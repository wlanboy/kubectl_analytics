"""Kubernetes data collection — core: namespaces, CRDs, adoption."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, cast

from kubernetes import client, config
from kubernetes.client import (
    V1CustomResourceDefinitionList,
    V1DeploymentList,
    V2HorizontalPodAutoscalerList,
    V1NamespaceList,
    V1NetworkPolicyList,
    V1PodDisruptionBudgetList,
    V1PodList,
)
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def load_config() -> None:
    """Load kubeconfig (in-cluster first, then local ~/.kube/config)."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class NamespaceInfo:
    name: str
    labels: dict[str, str]


@dataclass
class CRDStat:
    name: str           # e.g. certificates.cert-manager.io
    group: str
    kind: str
    plural: str
    namespaced: bool
    instances_by_namespace: dict[str, int] = field(default_factory=dict)

    @property
    def total_instances(self) -> int:
        return sum(self.instances_by_namespace.values())

    @property
    def namespace_count(self) -> int:
        return sum(1 for v in self.instances_by_namespace.values() if v > 0)


@dataclass
class AdoptionStat:
    namespace: str
    pod_count: int
    pods_with_limits: int
    has_network_policy: bool
    deployment_count: int
    pdb_count: int
    hpa_count: int
    flux_resources: int     # HelmReleases + Kustomizations
    argocd_resources: int   # Applications


# ---------------------------------------------------------------------------
# Namespace listing
# ---------------------------------------------------------------------------

def get_namespaces() -> list[NamespaceInfo]:
    v1 = client.CoreV1Api()
    ns_list = cast(V1NamespaceList, v1.list_namespace())
    return [
        NamespaceInfo(name=ns.metadata.name, labels=ns.metadata.labels or {})
        for ns in (ns_list.items or [])
    ]


# ---------------------------------------------------------------------------
# Shared helpers (used by CRD stats, adoption, and kubectl_istio)
# ---------------------------------------------------------------------------

def _custom_list(custom: client.CustomObjectsApi, *, group: str, version: str,
                 namespace: str | None, plural: str) -> dict[str, Any]:
    if namespace is not None:
        result = custom.list_namespaced_custom_object(
            group=group, version=version, namespace=namespace, plural=plural,
        )
    else:
        result = custom.list_cluster_custom_object(
            group=group, version=version, plural=plural,
        )
    return cast(dict[str, Any], result)


def _count_custom(custom: client.CustomObjectsApi, group: str, versions: list[str],
                  namespace: str, plural: str) -> int:
    for version in versions:
        try:
            result = _custom_list(
                custom, group=group, version=version, namespace=namespace, plural=plural,
            )
            return len(result.get("items", []))
        except ApiException as e:
            if e.status == 404:
                continue
    return 0


# ---------------------------------------------------------------------------
# CRD statistics
# ---------------------------------------------------------------------------

def _storage_version(crd: Any) -> str:
    for v in crd.spec.versions:
        if getattr(v, "storage", False):
            return v.name  # type: ignore[no-any-return]
    return crd.spec.versions[0].name if crd.spec.versions else "v1"  # type: ignore[no-any-return]


def get_crd_stats(namespace_names: list[str]) -> list[CRDStat]:
    ext = client.ApiextensionsV1Api()
    custom = client.CustomObjectsApi()

    crd_list = cast(V1CustomResourceDefinitionList, ext.list_custom_resource_definition())
    stats: list[CRDStat] = []

    for crd in (crd_list.items or []):
        spec = crd.spec
        version = _storage_version(crd)
        stat = CRDStat(
            name=crd.metadata.name,
            group=spec.group,
            kind=spec.names.kind,
            plural=spec.names.plural,
            namespaced=spec.scope == "Namespaced",
        )

        if stat.namespaced:
            for ns in namespace_names:
                try:
                    result = _custom_list(
                        custom, group=spec.group, version=version,
                        namespace=ns, plural=spec.names.plural,
                    )
                    count = len(result.get("items", []))
                    if count:
                        stat.instances_by_namespace[ns] = count
                except ApiException:
                    pass
        else:
            try:
                result = _custom_list(
                    custom, group=spec.group, version=version,
                    namespace=None, plural=spec.names.plural,
                )
                count = len(result.get("items", []))
                if count:
                    stat.instances_by_namespace["(cluster)"] = count
            except ApiException:
                pass

        if stat.total_instances > 0:
            stats.append(stat)

    return sorted(stats, key=lambda s: s.total_instances, reverse=True)


# ---------------------------------------------------------------------------
# Adoption metrics
# ---------------------------------------------------------------------------

def get_adoption_stats(namespace_names: list[str]) -> list[AdoptionStat]:
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    autoscaling = client.AutoscalingV2Api()
    networking = client.NetworkingV1Api()
    custom = client.CustomObjectsApi()

    try:
        policy = client.PolicyV1Api()
    except Exception:
        policy = None

    stats: list[AdoptionStat] = []

    for ns in namespace_names:
        try:
            pods = cast(V1PodList, v1.list_namespaced_pod(namespace=ns)).items or []
            pod_count = len(pods)
            pods_with_limits = sum(
                1 for pod in pods
                if all(
                    c.resources and c.resources.limits
                    and "cpu" in (c.resources.limits or {})
                    and "memory" in (c.resources.limits or {})
                    for c in pod.spec.containers
                )
            )

            net_policies = cast(V1NetworkPolicyList, networking.list_namespaced_network_policy(namespace=ns)).items or []
            has_network_policy = bool(net_policies)

            deployments = cast(V1DeploymentList, apps_v1.list_namespaced_deployment(namespace=ns)).items or []
            deployment_count = len(deployments)
            deployment_names = {d.metadata.name for d in deployments}

            pdb_count = 0
            if policy:
                try:
                    pdb_count = len(
                        cast(V1PodDisruptionBudgetList, policy.list_namespaced_pod_disruption_budget(namespace=ns)).items or []
                    )
                except ApiException:
                    pass

            hpas = cast(V2HorizontalPodAutoscalerList, autoscaling.list_namespaced_horizontal_pod_autoscaler(namespace=ns)).items or []
            hpa_targets = {h.spec.scale_target_ref.name for h in hpas}
            hpa_count = len(hpa_targets & deployment_names)

            flux_count = (
                _count_custom(custom, "helm.toolkit.fluxcd.io",
                              ["v2", "v2beta2", "v2beta1"], ns, "helmreleases")
                + _count_custom(custom, "kustomize.toolkit.fluxcd.io",
                                ["v1", "v1beta2", "v1beta1"], ns, "kustomizations")
            )

            argocd_count = _count_custom(
                custom, "argoproj.io", ["v1alpha1"], ns, "applications"
            )

            stats.append(AdoptionStat(
                namespace=ns,
                pod_count=pod_count,
                pods_with_limits=pods_with_limits,
                has_network_policy=has_network_policy,
                deployment_count=deployment_count,
                pdb_count=pdb_count,
                hpa_count=hpa_count,
                flux_resources=flux_count,
                argocd_resources=argocd_count,
            ))

        except ApiException as e:
            logger.warning("Skipping namespace %s: %s", ns, e)

    return stats
