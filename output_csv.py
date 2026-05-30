"""CSV serialization of report data."""
from __future__ import annotations

import csv
import io
from dataclasses import asdict

from kubectl import AdoptionStat, CRDStat, IstioNamespaceStat, ServiceEntryStat


def _buf(fields: list[str]) -> tuple[io.StringIO, csv.DictWriter]:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    return buf, writer


def render_crds(stats: list[CRDStat], total_namespaces: int) -> str:
    fields = ["name", "group", "kind", "namespace_count",
              "total_namespaces", "total_instances", "adoption_pct"]
    buf, writer = _buf(fields)
    for s in stats:
        pct = round(s.namespace_count * 100 / total_namespaces, 1) if total_namespaces else 0
        writer.writerow({
            "name": s.name,
            "group": s.group,
            "kind": s.kind,
            "namespace_count": s.namespace_count,
            "total_namespaces": total_namespaces,
            "total_instances": s.total_instances,
            "adoption_pct": pct,
        })
    return buf.getvalue()


def render_adoption(stats: list[AdoptionStat]) -> str:
    fields = [
        "namespace", "pod_count", "pods_with_limits", "has_network_policy",
        "deployment_count", "pdb_count", "hpa_count",
        "flux_resources", "argocd_resources",
    ]
    buf, writer = _buf(fields)
    for s in stats:
        writer.writerow(asdict(s))
    return buf.getvalue()


def render_istio(stats: list[IstioNamespaceStat]) -> str:
    fields = [
        "namespace", "injection_enabled", "pod_count", "sidecar_count",
        "virtual_services", "destination_rules", "gateways",
        "service_entries", "workload_entries",
        "peer_authentications", "authorization_policies", "mtls_mode",
    ]
    buf, writer = _buf(fields)
    for s in stats:
        writer.writerow(asdict(s))
    return buf.getvalue()


def render_service_entries(entries: list[ServiceEntryStat]) -> str:
    fields = ["namespace", "name", "hosts", "resolution", "ports"]
    buf, writer = _buf(fields)
    for e in entries:
        writer.writerow({
            "namespace": e.namespace,
            "name": e.name,
            "hosts": "; ".join(e.hosts),
            "resolution": e.resolution,
            "ports": "; ".join(e.ports),
        })
    return buf.getvalue()
