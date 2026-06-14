"""Rich table rendering — returns Table renderables, never prints directly."""
from __future__ import annotations

from rich import box
from rich.table import Table

from .kubectl import AdoptionStat, CRDStat
from .kubectl_deployments import WorkloadHealth
from .kubectl_events import EventDetail, EventNamespaceStat
from .kubectl_istio import IstioNamespaceStat, ServiceEntryStat
from .kubectl_logs import PodLogStat
from .kubectl_volumes import PVSummary, VolumeStat


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
        def _cell(n: int) -> str:
            return f"[green]{n}[/green]" if n != 0 else "[dim]0[/dim]"
        row = [ns] + [_cell(s.instances_by_namespace.get(ns, 0)) for s in stats]
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


# ---------------------------------------------------------------------------
# Volume mounts
# ---------------------------------------------------------------------------

def _gib(value: float) -> str:
    return f"{value:.1f} GiB" if value else "[dim]0[/dim]"


def render_volumes(stats: list[VolumeStat]) -> Table:
    table = Table(title="Volume Mounts per Namespace", box=box.SIMPLE_HEAD)
    table.add_column("NAMESPACE", style="cyan", no_wrap=True)
    table.add_column("PVCs", justify="right")
    table.add_column("BOUND", justify="right")
    table.add_column("PENDING", justify="right")
    table.add_column("REQUESTED", justify="right")
    table.add_column("CAPACITY", justify="right")

    for s in stats:
        table.add_row(
            s.namespace,
            str(s.pvc_count),
            str(s.bound),
            f"[yellow]{s.pending}[/yellow]" if s.pending else "[dim]0[/dim]",
            _gib(s.requested_gib),
            _gib(s.capacity_gib),
        )

    return table


# ---------------------------------------------------------------------------
# Pod log analysis
# ---------------------------------------------------------------------------

def render_logs(stats: list[PodLogStat]) -> Table:
    table = Table(title="Pod Log Analysis", box=box.SIMPLE_HEAD)
    table.add_column("NAMESPACE", style="cyan", no_wrap=True)
    table.add_column("POD", no_wrap=True)
    table.add_column("CONTAINER", no_wrap=True)
    table.add_column("LINES", justify="right")
    table.add_column("ERRORS", justify="right")
    table.add_column("WARNINGS", justify="right")
    table.add_column("TOP ERROR PATTERN")

    for s in stats:
        top = s.top_errors[0][0] if s.top_errors else "[dim]-[/dim]"
        errors_cell = f"[red]{s.error_count}[/red]" if s.error_count else "[dim]0[/dim]"
        warnings_cell = f"[yellow]{s.warning_count}[/yellow]" if s.warning_count else "[dim]0[/dim]"
        table.add_row(
            s.namespace,
            s.pod,
            s.container,
            str(s.total_lines),
            errors_cell,
            warnings_cell,
            top,
        )

    return table


def render_log_errors(stats: list[PodLogStat]) -> Table:
    table = Table(title="Log Error Patterns", box=box.SIMPLE_HEAD)
    table.add_column("NAMESPACE", style="cyan", no_wrap=True)
    table.add_column("POD", no_wrap=True)
    table.add_column("CONTAINER", no_wrap=True)
    table.add_column("COUNT", justify="right")
    table.add_column("PATTERN")

    for s in stats:
        for pattern, count in s.top_errors:
            table.add_row(
                s.namespace,
                s.pod,
                s.container,
                f"[red]{count}[/red]",
                pattern,
            )

    return table


# ---------------------------------------------------------------------------
# Kubernetes events
# ---------------------------------------------------------------------------

def render_events(stats: list[EventNamespaceStat]) -> Table:
    table = Table(title="Kubernetes Event Warnings per Namespace", box=box.SIMPLE_HEAD)
    table.add_column("NAMESPACE", style="cyan", no_wrap=True)
    table.add_column("TOTAL", justify="right")
    table.add_column("WARNINGS", justify="right")
    table.add_column("TOP REASONS")

    for s in stats:
        warnings_cell = (
            f"[red]{s.warning_count}[/red]" if s.warning_count else "[dim]0[/dim]"
        )
        reasons = ", ".join(f"{r}×{c}" for r, c in s.top_reasons) or "[dim]-[/dim]"
        table.add_row(s.namespace, str(s.total_events), warnings_cell, reasons)

    return table


def render_event_details(details: list[EventDetail]) -> Table:
    table = Table(title="Kubernetes Warning Event Details", box=box.SIMPLE_HEAD)
    table.add_column("NAMESPACE", style="cyan", no_wrap=True)
    table.add_column("KIND", no_wrap=True)
    table.add_column("OBJECT", no_wrap=True)
    table.add_column("REASON", style="yellow", no_wrap=True)
    table.add_column("COUNT", justify="right")
    table.add_column("COMPONENT", no_wrap=True)
    table.add_column("MESSAGE")

    for d in details:
        count_cell = f"[red]{d.count}[/red]" if d.count > 1 else str(d.count)
        table.add_row(
            d.namespace,
            d.object_kind,
            d.object_name,
            d.reason,
            count_cell,
            d.component,
            d.message,
        )

    return table


# ---------------------------------------------------------------------------
# Workload health
# ---------------------------------------------------------------------------

_PHASE_COLOR = {
    "Running": "green",
    "Succeeded": "dim",
    "Failed": "red",
    "Pending": "yellow",
    "Unknown": "yellow",
}

_STATE_COLOR = {
    "running": "green",
    "waiting": "yellow",
    "terminated": "dim",
    "unknown": "dim",
}


def render_workload_health(workloads: list[WorkloadHealth]) -> Table:
    table = Table(title="Workload Health Overview", box=box.SIMPLE_HEAD)
    table.add_column("NAMESPACE", style="cyan", no_wrap=True)
    table.add_column("KIND", no_wrap=True)
    table.add_column("WORKLOAD", no_wrap=True)
    table.add_column("DESIRED", justify="right")
    table.add_column("READY", justify="right")
    table.add_column("UNAVAIL", justify="right")
    table.add_column("RESTARTS", justify="right")
    table.add_column("STATUS", justify="center")

    for wl in workloads:
        unavail_cell = (
            f"[red]{wl.unavailable}[/red]" if wl.unavailable else "[dim]0[/dim]"
        )
        restarts_cell = (
            f"[yellow]{wl.total_restarts}[/yellow]"
            if wl.total_restarts else "[dim]0[/dim]"
        )
        status_cell = "[green]OK[/green]" if wl.is_healthy else "[red]DEGRADED[/red]"
        table.add_row(
            wl.namespace,
            wl.kind,
            wl.name,
            str(wl.desired),
            str(wl.ready),
            unavail_cell,
            restarts_cell,
            status_cell,
        )

    return table


def render_workload_containers(workloads: list[WorkloadHealth]) -> Table:
    table = Table(title="Pod & Container Health", box=box.SIMPLE_HEAD)
    table.add_column("NAMESPACE", style="cyan", no_wrap=True)
    table.add_column("WORKLOAD", no_wrap=True)
    table.add_column("POD", no_wrap=True)
    table.add_column("PHASE", justify="center")
    table.add_column("CONTAINER", no_wrap=True)
    table.add_column("INIT", justify="center")
    table.add_column("RESTARTS", justify="right")
    table.add_column("STATE", justify="center")
    table.add_column("REASON")

    for wl in workloads:
        for pod in wl.pods:
            phase_color = _PHASE_COLOR.get(pod.phase, "white")
            phase_cell = f"[{phase_color}]{pod.phase}[/{phase_color}]"
            if not pod.containers:
                table.add_row(
                    pod.namespace, wl.name, pod.name,
                    phase_cell, "[dim]-[/dim]", "", "", "", "",
                )
                continue
            for c in pod.containers:
                state_color = _STATE_COLOR.get(c.state, "white")
                if c.is_problem:
                    state_color = "red"
                state_cell = f"[{state_color}]{c.state}[/{state_color}]"
                reason_cell = (
                    f"[red]{c.reason}[/red]" if c.is_problem
                    else (f"[dim]{c.reason}[/dim]" if c.reason else "[dim]-[/dim]")
                )
                restarts_cell = (
                    f"[red]{c.restart_count}[/red]" if c.restart_count > 0
                    else "[dim]0[/dim]"
                )
                init_cell = "[dim]init[/dim]" if c.is_init else ""
                table.add_row(
                    pod.namespace,
                    wl.name,
                    pod.name,
                    phase_cell,
                    c.name,
                    init_cell,
                    restarts_cell,
                    state_cell,
                    reason_cell,
                )

    return table


def render_pv_summary(summary: PVSummary) -> Table:
    table = Table(title="Persistent Volume Cluster Summary", box=box.SIMPLE_HEAD)
    table.add_column("TOTAL PVs", justify="right")
    table.add_column("CAPACITY", justify="right")
    table.add_column("BOUND", justify="right")
    table.add_column("AVAILABLE PVs", justify="right")
    table.add_column("FREE", justify="right")

    table.add_row(
        str(summary.total_pvs),
        _gib(summary.total_capacity_gib),
        str(summary.bound_pvs),
        str(summary.available_pvs),
        _gib(summary.available_gib),
    )

    return table
