"""kubectl analytics — TUI entry point."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from . import (
    kubectl,
    kubectl_deployments,
    kubectl_events,
    kubectl_istio,
    kubectl_logs,
    kubectl_volumes,
    output_csv,
    output_table,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="analytics",
    help="Kubernetes adoption and mesh statistics — per namespace.",
    add_completion=False,
)
console = Console()


class OutputFormat(str, Enum):
    table = "table"
    csv = "csv"


_SINCE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


@dataclass
class OutputTarget:
    """Where a command's rendered result should go."""
    fmt: OutputFormat
    dir: Path | None = None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _bootstrap() -> None:
    try:
        kubectl.load_config()
    except Exception as e:
        console.print(f"[red]Cannot load kubeconfig:[/red] {e}")
        raise typer.Exit(1)


def _resolve_namespaces(namespace: str | None) -> tuple[list[kubectl.NamespaceInfo], list[str]]:
    """Bootstrap, list namespaces, and resolve the --namespace filter.

    Returns both the NamespaceInfo objects (for label-aware callers like
    istio) and the plain names (for callers that only need the name).
    """
    _bootstrap()
    all_namespaces = kubectl.get_namespaces()
    ns_names = [namespace] if namespace else [ns.name for ns in all_namespaces]
    namespaces = [ns for ns in all_namespaces if ns.name in ns_names]
    return namespaces, ns_names


def _parse_since_seconds(since: str | None) -> int | None:
    """Parse a duration like '1h', '30m', '5m' into seconds."""
    if not since:
        return None
    unit = since[-1].lower()
    if unit in _SINCE_UNITS and since[:-1].isdigit():
        return int(since[:-1]) * _SINCE_UNITS[unit]
    console.print(f"[red]Invalid --since value:[/red] {since!r}  "
                  "(use e.g. 1h, 30m, 5m)")
    raise typer.Exit(1)


def _emit(content: str, name: str, target: OutputTarget) -> None:
    if target.dir:
        target.dir.mkdir(parents=True, exist_ok=True)
        (target.dir / f"{name}.csv").write_text(content, encoding="utf-8")
    else:
        print(content, end="")


def _render(data, target: OutputTarget, name: str, table_fn, csv_fn) -> None:
    if target.fmt == OutputFormat.table:
        console.print(table_fn(data))
    else:
        _emit(csv_fn(data), name, target)


# ---------------------------------------------------------------------------
# crds command
# ---------------------------------------------------------------------------

@app.command()
def crds(
    namespace: Annotated[str | None, typer.Option(
        "--namespace", "-n", help="Limit to one namespace")] = None,
    breakdown: Annotated[bool, typer.Option(
        "--breakdown", help="Also show per-namespace instance matrix")] = False,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Path | None, typer.Option(
        "--output-dir")] = None,
) -> None:
    """CRD adoption rate across namespaces."""
    _, ns_names = _resolve_namespaces(namespace)
    target = OutputTarget(output, output_dir)
    total = len(ns_names)

    with console.status("Collecting CRD statistics…"):
        stats = kubectl.get_crd_stats(ns_names)

    if target.fmt == OutputFormat.table:
        console.print(output_table.render_crds(stats, total))
        if breakdown:
            console.print(output_table.render_crds_per_namespace(stats, ns_names))
    else:
        _emit(output_csv.render_crds(stats, total), "crds", target)


# ---------------------------------------------------------------------------
# adoption command
# ---------------------------------------------------------------------------

@app.command()
def adoption(
    namespace: Annotated[str | None, typer.Option(
        "--namespace", "-n")] = None,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Path | None, typer.Option(
        "--output-dir")] = None,
) -> None:
    """Adoption rate metrics per namespace."""
    _, ns_names = _resolve_namespaces(namespace)
    target = OutputTarget(output, output_dir)

    with console.status("Collecting adoption metrics…"):
        stats = kubectl.get_adoption_stats(ns_names)

    _render(
        stats, target, "adoption",
        output_table.render_adoption,
        output_csv.render_adoption,
    )


# ---------------------------------------------------------------------------
# istio command
# ---------------------------------------------------------------------------

@app.command()
def istio(
    traffic: Annotated[bool, typer.Option(
        "--traffic", help="Show traffic policies (VS, DR, Gateways)")] = False,
    external: Annotated[bool, typer.Option(
        "--external", help="Show external services (ServiceEntries)")] = False,
    policies: Annotated[bool, typer.Option(
        "--policies", help="Show security policies (mTLS, AuthzPolicies)")] = False,
    namespace: Annotated[str | None, typer.Option(
        "--namespace", "-n")] = None,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Path | None, typer.Option(
        "--output-dir")] = None,
) -> None:
    """Istio service mesh usage per namespace."""
    namespaces, ns_names = _resolve_namespaces(namespace)
    target = OutputTarget(output, output_dir)

    with console.status("Collecting Istio statistics…"):
        stats = kubectl_istio.get_istio_stats(namespaces)

    # Default: show enrollment when no specific flag is given
    show_enrollment = not any([traffic, external, policies])

    if show_enrollment:
        _render(
            stats, target, "istio",
            output_table.render_istio,
            output_csv.render_istio,
        )

    if traffic:
        _render(
            stats, target, "istio-traffic",
            output_table.render_istio_traffic,
            output_csv.render_istio_traffic,
        )

    if policies:
        _render(
            stats, target, "istio-policies",
            output_table.render_istio_policies,
            output_csv.render_istio_policies,
        )

    if external:
        with console.status("Collecting ServiceEntries…"):
            entries = kubectl_istio.get_service_entries(ns_names)
        _render(
            entries, target, "istio-external",
            output_table.render_service_entries,
            output_csv.render_service_entries,
        )

# ---------------------------------------------------------------------------
# volumes command
# ---------------------------------------------------------------------------

@app.command()
def volumes(
    namespace: Annotated[str | None, typer.Option(
        "--namespace", "-n", help="Limit to one namespace")] = None,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Path | None, typer.Option(
        "--output-dir")] = None,
) -> None:
    """Volume mount statistics per namespace."""
    _, ns_names = _resolve_namespaces(namespace)
    target = OutputTarget(output, output_dir)

    with console.status("Collecting volume statistics…"):
        stats, pv_summary = kubectl_volumes.get_volume_stats(ns_names)

    if target.fmt == OutputFormat.table:
        console.print(output_table.render_volumes(stats))
        console.print(output_table.render_pv_summary(pv_summary))
    else:
        _emit(output_csv.render_volumes(stats), "volumes", target)
        _emit(output_csv.render_pv_summary(pv_summary), "volumes-pv-summary", target)


# ---------------------------------------------------------------------------
# logs command
# ---------------------------------------------------------------------------

@app.command()
def logs(
    namespace: Annotated[str | None, typer.Option(
        "--namespace", "-n", help="Limit to one namespace")] = None,
    tail: Annotated[int, typer.Option(
        "--tail", help="Number of log lines to fetch per pod")] = 100,
    since: Annotated[str | None, typer.Option(
        "--since", help="Only return logs newer than this duration (e.g. 1h, 30m, 5m)")] = None,
    errors: Annotated[bool, typer.Option(
        "--errors", help="Also show top error pattern breakdown")] = False,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Path | None, typer.Option(
        "--output-dir")] = None,
) -> None:
    """Collect and analyze pod logs per namespace."""
    since_seconds = _parse_since_seconds(since)
    _, ns_names = _resolve_namespaces(namespace)
    target = OutputTarget(output, output_dir)

    with console.status("Collecting pod logs…"):
        stats = kubectl_logs.get_log_stats(
            ns_names, tail_lines=tail, since_seconds=since_seconds,
        )

    if target.fmt == OutputFormat.table:
        console.print(output_table.render_logs(stats))
        if errors:
            pods_with_errors = [s for s in stats if s.top_errors]
            if pods_with_errors:
                console.print(output_table.render_log_errors(pods_with_errors))
    else:
        _emit(output_csv.render_logs(stats), "logs", target)


# ---------------------------------------------------------------------------
# events command
# ---------------------------------------------------------------------------

@app.command()
def events(
    namespace: Annotated[str | None, typer.Option(
        "--namespace", "-n", help="Limit to one namespace")] = None,
    since: Annotated[str | None, typer.Option(
        "--since", help="Only include events newer than this duration (e.g. 1h, 30m, 5m)")] = None,
    details: Annotated[bool, typer.Option(
        "--details", help="Show individual warning events (sorted by count)")] = False,
    all_events: Annotated[bool, typer.Option(
        "--all-events", help="Include Normal events in --details (default: warnings only)")] = False,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Path | None, typer.Option(
        "--output-dir")] = None,
) -> None:
    """Inspect Kubernetes events to detect warnings and failure patterns."""
    since_seconds = _parse_since_seconds(since)
    _, ns_names = _resolve_namespaces(namespace)
    target = OutputTarget(output, output_dir)

    with console.status("Collecting Kubernetes events…"):
        stats = kubectl_events.get_event_stats(ns_names, since_seconds=since_seconds)

    event_details = None
    if details:
        with console.status("Collecting event details…"):
            event_details = kubectl_events.get_event_details(
                ns_names, since_seconds=since_seconds,
                warnings_only=not all_events,
            )

    if target.fmt == OutputFormat.table:
        console.print(output_table.render_events(stats))
        if event_details:
            console.print(output_table.render_event_details(event_details))
    else:
        _emit(output_csv.render_events(stats), "events", target)
        if event_details is not None:
            _emit(output_csv.render_event_details(event_details), "events-details", target)


# ---------------------------------------------------------------------------
# deployments command
# ---------------------------------------------------------------------------

@app.command()
def deployments(
    namespace: Annotated[str | None, typer.Option(
        "--namespace", "-n", help="Limit to one namespace")] = None,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Path | None, typer.Option(
        "--output-dir")] = None,
) -> None:
    """Workload health for Deployments, StatefulSets and DaemonSets with pod and container detail."""
    _, ns_names = _resolve_namespaces(namespace)
    target = OutputTarget(output, output_dir)

    with console.status("Collecting workload health…"):
        workloads = kubectl_deployments.get_workload_health(ns_names)

    if target.fmt == OutputFormat.table:
        console.print(output_table.render_workload_health(workloads))
        console.print(output_table.render_workload_containers(workloads))
    else:
        _emit(output_csv.render_workloads(workloads), "workloads", target)
        _emit(output_csv.render_workload_containers(workloads),
              "workload-containers", target)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app()


if __name__ == "__main__":
    main()
