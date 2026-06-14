"""Kubernetes data collection — Istio service mesh."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from kubernetes import client
from kubernetes.client import V1PodList
from kubernetes.client.rest import ApiException

from .kubectl import NamespaceInfo, _count_custom, _custom_list


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

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
# Helpers
# ---------------------------------------------------------------------------

def _istio_count(custom: client.CustomObjectsApi, group: str,
                 namespace: str, plural: str) -> int:
    return _count_custom(custom, group, ["v1", "v1beta1", "v1alpha3"], namespace, plural)


def _mtls_mode(custom: client.CustomObjectsApi, namespace: str) -> str:
    for version in ["v1", "v1beta1"]:
        try:
            result = _custom_list(
                custom, group="security.istio.io", version=version,
                namespace=namespace, plural="peerauthentications",
            )
            items: list[dict[str, Any]] = result.get("items", [])
            if not items:
                return "none"
            for item in items:
                if not item.get("spec", {}).get("selector"):
                    return str(item.get("spec", {}).get("mtls", {}).get("mode", "none"))
            return str(items[0].get("spec", {}).get("mtls", {}).get("mode", "none"))
        except ApiException as e:
            if e.status == 404:
                continue
    return "none"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_istio_stats(namespace_infos: list[NamespaceInfo]) -> list[IstioNamespaceStat]:
    v1 = client.CoreV1Api()
    custom = client.CustomObjectsApi()
    stats: list[IstioNamespaceStat] = []

    for ns_info in namespace_infos:
        ns = ns_info.name
        injection_enabled = ns_info.labels.get("istio-injection") == "enabled"

        try:
            pods = cast(V1PodList, v1.list_namespaced_pod(namespace=ns)).items or []
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


def get_service_entries(namespace_names: list[str]) -> list[ServiceEntryStat]:
    custom = client.CustomObjectsApi()
    entries: list[ServiceEntryStat] = []

    for ns in namespace_names:
        for version in ["v1", "v1beta1", "v1alpha3"]:
            try:
                result = _custom_list(
                    custom, group="networking.istio.io", version=version,
                    namespace=ns, plural="serviceentries",
                )
                for item in result.get("items", []):
                    spec: dict[str, Any] = item.get("spec", {})
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
                break
            except ApiException as e:
                if e.status == 404:
                    continue

    return entries
