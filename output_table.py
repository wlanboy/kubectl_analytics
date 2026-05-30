"""Rich table rendering — returns Table renderables, never prints directly."""
from __future__ import annotations

from rich import box
from rich.table import Table

from kubectl import (
    AdoptionStat,
    CRDStat,
    IstioNamespaceStat,
    ServiceEntryStat,
)


def _pct(part: int, total: int) -> str:
    if total == 0:
        return "n/a"
    return f"{part * 100 // total}%"


def _yn(value: bool, *, color: bool = True) -> str:
    if value:
        return "[green]yes[/green]" if color else "yes"
    return "[red]no[/red]" if color else "no"


# ---------------------------------------------------------------------------
# CRD adoption
# ---------------------------------------------------------------------------

def render_crds(stats: list[CRDStat], total_namespaces: int) -> Table:
    table = Table(
        title="Custom Resource Adoption",
        box=box.SIMPLE_HEAD,
        show_lines=False,
    )
    table.add_column("CRD", style="cyan", no_wrap=True)
    table.add_column("NAMESPACES", justify="right")
    table.add_column("INSTANCES", justify="right")
    table.add_column("ADOPTION", justify="right")

    for s in stats:
        table.add_row(
            s.name,
            f"{s.namespace_count} / {total_namespaces}",
            str(s.total_instances),
            _pct(s.namespace_count, total_namespaces),
        )

    return table


def render_crds_per_namespace(stats: list[CRDStat],
                               namespace_names: list[str]) -> Table:
    """Per-namespace breakdown: rows = namespaces, columns = CRDs."""
    table = Table(
        title="CRD Instances per Namespace",
        box=box.SIMPLE_HEAD,
    )
    table.add_column("NAMESPACE", style="cyan", no_wrap=True)
    for s in stats:
        # Shorten to last two dot-segments for readability
        label = ".".join(s.name.split(".")[:2])
        table.add_column(label, justify="right")

    for ns in namespace_names:
        row = [ns] + [str(s.instances_by_namespace.get(ns, 0)) for s in stats]
        table.add_row(*row)

    return table


# ---------------------------------------------------------------------------
# Adoption rate
# ---------------------------------------------------------------------------

def render_adoption(stats: list[AdoptionStat]) -> Table:
    table = Table(
        title="Adoption Rate per Namespace",
        box=box.SIMPLE_HEAD,
    )
    table.add_column("NAMESPACE", style="cyan", no_wrap=True)
    table.add_column("PODS", justify="right")
    table.add_column("LIMITS", justify="right")
    table.add_column("NETPOL", justify="center")
    table.add_column("DEPLOYS", justify="right")
    table.add_column("PDB", justify="right")
    table.add_column("HPA", justify="right")
    table.add_column("FLUX", justify="right")
    table.add_column("ARGO", justify="right")

    for s in stats:
        table.add_row(
            s.namespace,
            str(s.pod_count),
            f"{s.pods_with_limits}/{s.pod_count}",
            _yn(s.has_network_policy),
            str(s.deployment_count),
            str(s.pdb_count),
            str(s.hpa_count),
            str(s.flux_resources),
            str(s.argocd_resources),
        )

    return table


# ---------------------------------------------------------------------------
# Istio enrollment
# ---------------------------------------------------------------------------

def render_istio(stats: list[IstioNamespaceStat]) -> Table:
    table = Table(
        title="Istio Namespace Enrollment",
        box=box.SIMPLE_HEAD,
    )
    table.add_column("NAMESPACE", style="cyan", no_wrap=True)
    table.add_column("INJECTION", justify="center")
    table.add_column("SIDECARS", justify="right")
    table.add_column("PODS", justify="right")
    table.add_column("COVERAGE", justify="right")

    for s in stats:
        coverage = _pct(s.sidecar_count, s.pod_count)
        table.add_row(
            s.namespace,
            _yn(s.injection_enabled),
            str(s.sidecar_count),
            str(s.pod_count),
            coverage,
        )

    return table


# ---------------------------------------------------------------------------
# Istio traffic policies
# ---------------------------------------------------------------------------

def render_istio_traffic(stats: list[IstioNamespaceStat]) -> Table:
    table = Table(
        title="Istio Traffic Policies per Namespace",
        box=box.SIMPLE_HEAD,
    )
    table.add_column("NAMESPACE", style="cyan", no_wrap=True)
    table.add_column("VirtualServices", justify="right")
    table.add_column("DestinationRules", justify="right")
    table.add_column("Gateways", justify="right")
    table.add_column("ServiceEntries", justify="right")
    table.add_column("WorkloadEntries", justify="right")

    for s in stats:
        table.add_row(
            s.namespace,
            str(s.virtual_services),
            str(s.destination_rules),
            str(s.gateways),
            str(s.service_entries),
            str(s.workload_entries),
        )

    return table


# ---------------------------------------------------------------------------
# Istio security policies
# ---------------------------------------------------------------------------

def render_istio_policies(stats: list[IstioNamespaceStat]) -> Table:
    table = Table(
        title="Istio Security Policies per Namespace",
        box=box.SIMPLE_HEAD,
    )
    table.add_column("NAMESPACE", style="cyan", no_wrap=True)
    table.add_column("PeerAuthentication", justify="right")
    table.add_column("AuthorizationPolicies", justify="right")
    table.add_column("mTLS-MODE", justify="center")

    _mode_color = {
        "STRICT": "green",
        "PERMISSIVE": "yellow",
        "DISABLE": "red",
        "none": "dim",
    }

    for s in stats:
        color = _mode_color.get(s.mtls_mode, "white")
        table.add_row(
            s.namespace,
            str(s.peer_authentications),
            str(s.authorization_policies),
            f"[{color}]{s.mtls_mode}[/{color}]",
        )

    return table


# ---------------------------------------------------------------------------
# External services (ServiceEntries)
# ---------------------------------------------------------------------------

def render_service_entries(entries: list[ServiceEntryStat]) -> Table:
    table = Table(
        title="Istio External Services (ServiceEntries)",
        box=box.SIMPLE_HEAD,
    )
    table.add_column("NAMESPACE", style="cyan", no_wrap=True)
    table.add_column("NAME", no_wrap=True)
    table.add_column("HOSTS")
    table.add_column("RESOLUTION", justify="center")
    table.add_column("PORTS")

    for e in entries:
        table.add_row(
            e.namespace,
            e.name,
            ", ".join(e.hosts),
            e.resolution,
            ", ".join(e.ports),
        )

    return table
