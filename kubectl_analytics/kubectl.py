"""Kubernetes data collection via the official Python client."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from kubernetes import client, config
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


@dataclass
class IstioNamespaceStat:
    namespace: str
    injection_enabled: bool
    pod_count: int
    sidecar_count: int
    virtual_services: int
    destination_rules: int
    gateways: int
    service_entries: int
    workload_entries: int
    peer_authentications: int
    authorization_policies: int
    mtls_mode: str          # STRICT | PERMISSIVE | DISABLE | none


@dataclass
class ServiceEntryStat:
    namespace: str
    name: str
    hosts: list[str]
    resolution: str
    ports: list[str]


# ---------------------------------------------------------------------------
# Namespace listing
# ---------------------------------------------------------------------------

def get_namespaces() -> list[NamespaceInfo]:
    v1 = client.CoreV1Api()
    return [
        NamespaceInfo(name=ns.metadata.name, labels=ns.metadata.labels or {})
        for ns in v1.list_namespace().items
    ]


# ---------------------------------------------------------------------------
# CRD statistics
# ---------------------------------------------------------------------------

def _storage_version(crd) -> str:
    for v in crd.spec.versions:
        if getattr(v, "storage", False):
            return v.name
    return crd.spec.versions[0].name if crd.spec.versions else "v1"


def get_crd_stats(namespace_names: list[str]) -> list[CRDStat]:
    ext = client.ApiextensionsV1Api()
    custom = client.CustomObjectsApi()

    stats: list[CRDStat] = []

    for crd in ext.list_custom_resource_definition().items:
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
                    result = custom.list_namespaced_custom_object(
                        group=spec.group, version=version,
                        namespace=ns, plural=spec.names.plural,
                    )
                    count = len(result.get("items", []))
                    if count:
                        stat.instances_by_namespace[ns] = count
                except ApiException:
                    pass
        else:
            try:
                result = custom.list_cluster_custom_object(
                    group=spec.group, version=version, plural=spec.names.plural,
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

def _count_custom(custom: client.CustomObjectsApi, group: str, versions: list[str],
                  namespace: str, plural: str) -> int:
    for version in versions:
        try:
            result = custom.list_namespaced_custom_object(
                group=group, version=version, namespace=namespace, plural=plural,
            )
            return len(result.get("items", []))
        except ApiException as e:
            if e.status == 404:
                continue
    return 0


def get_adoption_stats(namespace_names: list[str]) -> list[AdoptionStat]:
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    autoscaling = client.AutoscalingV1Api()
    networking = client.NetworkingV1Api()
    custom = client.CustomObjectsApi()

    try:
        policy = client.PolicyV1Api()
    except Exception:
        policy = None

    stats: list[AdoptionStat] = []

    for ns in namespace_names:
        try:
            pods = v1.list_namespaced_pod(namespace=ns).items
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

            net_policies = networking.list_namespaced_network_policy(namespace=ns).items
            has_network_policy = bool(net_policies)

            deployments = apps_v1.list_namespaced_deployment(namespace=ns).items
            deployment_count = len(deployments)
            deployment_names = {d.metadata.name for d in deployments}

            pdb_count = 0
            if policy:
                try:
                    pdb_count = len(
                        policy.list_namespaced_pod_disruption_budget(namespace=ns).items
                    )
                except ApiException:
                    pass

            hpas = autoscaling.list_namespaced_horizontal_pod_autoscaler(namespace=ns).items
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


# ---------------------------------------------------------------------------
# Istio statistics
# ---------------------------------------------------------------------------

def _istio_count(custom: client.CustomObjectsApi, group: str,
                 namespace: str, plural: str) -> int:
    return _count_custom(custom, group, ["v1", "v1beta1", "v1alpha3"], namespace, plural)


def _mtls_mode(custom: client.CustomObjectsApi, namespace: str) -> str:
    for version in ["v1", "v1beta1"]:
        try:
            result = custom.list_namespaced_custom_object(
                group="security.istio.io", version=version,
                namespace=namespace, plural="peerauthentications",
            )
            items = result.get("items", [])
            if not items:
                return "none"
            # Prefer the namespace-wide policy (no workload selector)
            for item in items:
                if not item.get("spec", {}).get("selector"):
                    return item.get("spec", {}).get("mtls", {}).get("mode", "none")
            return items[0].get("spec", {}).get("mtls", {}).get("mode", "none")
        except ApiException as e:
            if e.status == 404:
                continue
    return "none"


def get_istio_stats(namespace_infos: list[NamespaceInfo]) -> list[IstioNamespaceStat]:
    v1 = client.CoreV1Api()
    custom = client.CustomObjectsApi()
    stats: list[IstioNamespaceStat] = []

    for ns_info in namespace_infos:
        ns = ns_info.name
        injection_enabled = ns_info.labels.get("istio-injection") == "enabled"

        try:
            pods = v1.list_namespaced_pod(namespace=ns).items
        except ApiException:
            continue

        pod_count = len(pods)
        sidecar_count = sum(
            1 for pod in pods
            if any(c.name == "istio-proxy" for c in (pod.spec.containers or []))
        )

        stats.append(IstioNamespaceStat(
            namespace=ns,
            injection_enabled=injection_enabled,
            pod_count=pod_count,
            sidecar_count=sidecar_count,
            virtual_services=_istio_count(
                custom, "networking.istio.io", ns, "virtualservices"),
            destination_rules=_istio_count(
                custom, "networking.istio.io", ns, "destinationrules"),
            gateways=_istio_count(
                custom, "networking.istio.io", ns, "gateways"),
            service_entries=_istio_count(
                custom, "networking.istio.io", ns, "serviceentries"),
            workload_entries=_istio_count(
                custom, "networking.istio.io", ns, "workloadentries"),
            peer_authentications=_istio_count(
                custom, "security.istio.io", ns, "peerauthentications"),
            authorization_policies=_istio_count(
                custom, "security.istio.io", ns, "authorizationpolicies"),
            mtls_mode=_mtls_mode(custom, ns),
        ))

    return stats


# ---------------------------------------------------------------------------
# Service entries (external services)
# ---------------------------------------------------------------------------

def get_service_entries(namespace_names: list[str]) -> list[ServiceEntryStat]:
    custom = client.CustomObjectsApi()
    entries: list[ServiceEntryStat] = []

    for ns in namespace_names:
        for version in ["v1", "v1beta1", "v1alpha3"]:
            try:
                result = custom.list_namespaced_custom_object(
                    group="networking.istio.io", version=version,
                    namespace=ns, plural="serviceentries",
                )
                for item in result.get("items", []):
                    spec = item.get("spec", {})
                    ports = [
                        f"{p.get('number')}/{p.get('protocol', 'TCP')}"
                        for p in spec.get("ports", [])
                    ]
                    entries.append(ServiceEntryStat(
                        namespace=ns,
                        name=item["metadata"]["name"],
                        hosts=spec.get("hosts", []),
                        resolution=spec.get("resolution", "NONE"),
                        ports=ports,
                    ))
                break   # found a working version
            except ApiException as e:
                if e.status == 404:
                    continue

    return entries
