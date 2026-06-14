"""kubectl analytics — TUI entry point."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from . import kubectl
from . import kubectl_deployments
from . import kubectl_events
from . import kubectl_istio
from . import kubectl_logs
from . import kubectl_volumes
from . import output_csv
from . import output_table

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


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _bootstrap() -> None:
    try:
        kubectl.load_config()
    except Exception as e:
        console.print(f"[red]Cannot load kubeconfig:[/red] {e}")
        raise typer.Exit(1)


def _emit(content: str, name: str, output_dir: Optional[Path]) -> None:
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{name}.csv").write_text(content, encoding="utf-8")
    else:
        print(content, end="")


def _render(data, fmt: OutputFormat, name: str, output_dir: Optional[Path],
            table_fn, csv_fn) -> None:
    if fmt == OutputFormat.table:
        console.print(table_fn(data))
    else:
        _emit(csv_fn(data), name, output_dir)


# ---------------------------------------------------------------------------
# crds command
# ---------------------------------------------------------------------------

@app.command()
def crds(
    namespace: Annotated[Optional[str], typer.Option(
        "--namespace", "-n", help="Limit to one namespace")] = None,
    breakdown: Annotated[bool, typer.Option(
        "--breakdown", help="Also show per-namespace instance matrix")] = False,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Optional[Path], typer.Option(
        "--output-dir")] = None,
) -> None:
    """CRD adoption rate across namespaces."""
    _bootstrap()

    namespaces = kubectl.get_namespaces()
    ns_names = [namespace] if namespace else [ns.name for ns in namespaces]
    total = len(ns_names)

    with console.status("Collecting CRD statistics…"):
        stats = kubectl.get_crd_stats(ns_names)

    if output == OutputFormat.table:
        console.print(output_table.render_crds(stats, total))
        if breakdown:
            console.print(output_table.render_crds_per_namespace(stats, ns_names))
    else:
        _emit(output_csv.render_crds(stats, total), "crds", output_dir)


# ---------------------------------------------------------------------------
# adoption command
# ---------------------------------------------------------------------------

@app.command()
def adoption(
    namespace: Annotated[Optional[str], typer.Option(
        "--namespace", "-n")] = None,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Optional[Path], typer.Option(
        "--output-dir")] = None,
) -> None:
    """Adoption rate metrics per namespace."""
    _bootstrap()

    namespaces = kubectl.get_namespaces()
    ns_names = [namespace] if namespace else [ns.name for ns in namespaces]

    with console.status("Collecting adoption metrics…"):
        stats = kubectl.get_adoption_stats(ns_names)

    _render(
        stats, output, "adoption", output_dir,
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
    namespace: Annotated[Optional[str], typer.Option(
        "--namespace", "-n")] = None,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Optional[Path], typer.Option(
        "--output-dir")] = None,
) -> None:
    """Istio service mesh usage per namespace."""
    _bootstrap()

    namespaces = kubectl.get_namespaces()
    if namespace:
        namespaces = [ns for ns in namespaces if ns.name == namespace]

    with console.status("Collecting Istio statistics…"):
        stats = kubectl_istio.get_istio_stats(namespaces)

    # Default: show enrollment when no specific flag is given
    show_enrollment = not any([traffic, external, policies])

    if show_enrollment:
        _render(
            stats, output, "istio", output_dir,
            output_table.render_istio,
            output_csv.render_istio,
        )

    if traffic:
        _render(
            stats, output, "istio-traffic", output_dir,
            output_table.render_istio_traffic,
            output_csv.render_istio,
        )

    if policies:
        _render(
            stats, output, "istio-policies", output_dir,
            output_table.render_istio_policies,
            output_csv.render_istio,
        )

    if external:
        ns_names = [ns.name for ns in namespaces]
        with console.status("Collecting ServiceEntries…"):
            entries = kubectl_istio.get_service_entries(ns_names)
        _render(
            entries, output, "istio-external", output_dir,
            output_table.render_service_entries,
            output_csv.render_service_entries,
        )

# ---------------------------------------------------------------------------
# volumes command
# ---------------------------------------------------------------------------

@app.command()
def volumes(
    namespace: Annotated[Optional[str], typer.Option(
        "--namespace", "-n", help="Limit to one namespace")] = None,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Optional[Path], typer.Option(
        "--output-dir")] = None,
) -> None:
    """Volume mount statistics per namespace."""
    _bootstrap()

    namespaces = kubectl.get_namespaces()
    ns_names = [namespace] if namespace else [ns.name for ns in namespaces]

    with console.status("Collecting volume statistics…"):
        stats, pv_summary = kubectl_volumes.get_volume_stats(ns_names)

    if output == OutputFormat.table:
        console.print(output_table.render_volumes(stats))
        console.print(output_table.render_pv_summary(pv_summary))
    else:
        _emit(output_csv.render_volumes(stats), "volumes", output_dir)
        _emit(output_csv.render_pv_summary(pv_summary), "volumes-pv-summary", output_dir)


# ---------------------------------------------------------------------------
# logs command
# ---------------------------------------------------------------------------

@app.command()
def logs(
    namespace: Annotated[Optional[str], typer.Option(
        "--namespace", "-n", help="Limit to one namespace")] = None,
    tail: Annotated[int, typer.Option(
        "--tail", help="Number of log lines to fetch per pod")] = 100,
    since: Annotated[Optional[str], typer.Option(
        "--since", help="Only return logs newer than this duration (e.g. 1h, 30m, 5m)")] = None,
    errors: Annotated[bool, typer.Option(
        "--errors", help="Also show top error pattern breakdown")] = False,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Optional[Path], typer.Option(
        "--output-dir")] = None,
) -> None:
    """Collect and analyze pod logs per namespace."""
    _bootstrap()

    since_seconds: Optional[int] = None
    if since:
        _units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        unit = since[-1].lower()
        if unit in _units and since[:-1].isdigit():
            since_seconds = int(since[:-1]) * _units[unit]
        else:
            console.print(f"[red]Invalid --since value:[/red] {since!r}  "
                          "(use e.g. 1h, 30m, 5m)")
            raise typer.Exit(1)

    namespaces = kubectl.get_namespaces()
    ns_names = [namespace] if namespace else [ns.name for ns in namespaces]

    with console.status("Collecting pod logs…"):
        stats = kubectl_logs.get_log_stats(
            ns_names, tail_lines=tail, since_seconds=since_seconds,
        )

    if output == OutputFormat.table:
        console.print(output_table.render_logs(stats))
        if errors:
            pods_with_errors = [s for s in stats if s.top_errors]
            if pods_with_errors:
                console.print(output_table.render_log_errors(pods_with_errors))
    else:
        _emit(output_csv.render_logs(stats), "logs", output_dir)


# ---------------------------------------------------------------------------
# events command
# ---------------------------------------------------------------------------

@app.command()
def events(
    namespace: Annotated[Optional[str], typer.Option(
        "--namespace", "-n", help="Limit to one namespace")] = None,
    since: Annotated[Optional[str], typer.Option(
        "--since", help="Only include events newer than this duration (e.g. 1h, 30m, 5m)")] = None,
    details: Annotated[bool, typer.Option(
        "--details", help="Show individual warning events (sorted by count)")] = False,
    all_events: Annotated[bool, typer.Option(
        "--all-events", help="Include Normal events in --details (default: warnings only)")] = False,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Optional[Path], typer.Option(
        "--output-dir")] = None,
) -> None:
    """Inspect Kubernetes events to detect warnings and failure patterns."""
    _bootstrap()

    since_seconds: Optional[int] = None
    if since:
        _units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        unit = since[-1].lower()
        if unit in _units and since[:-1].isdigit():
            since_seconds = int(since[:-1]) * _units[unit]
        else:
            console.print(f"[red]Invalid --since value:[/red] {since!r}  "
                          "(use e.g. 1h, 30m, 5m)")
            raise typer.Exit(1)

    namespaces = kubectl.get_namespaces()
    ns_names = [namespace] if namespace else [ns.name for ns in namespaces]

    with console.status("Collecting Kubernetes events…"):
        stats = kubectl_events.get_event_stats(ns_names, since_seconds=since_seconds)

    if output == OutputFormat.table:
        console.print(output_table.render_events(stats))
        if details:
            with console.status("Collecting event details…"):
                event_details = kubectl_events.get_event_details(
                    ns_names, since_seconds=since_seconds,
                    warnings_only=not all_events,
                )
            if event_details:
                console.print(output_table.render_event_details(event_details))
    else:
        _emit(output_csv.render_events(stats), "events", output_dir)
        if details:
            with console.status("Collecting event details…"):
                event_details = kubectl_events.get_event_details(
                    ns_names, since_seconds=since_seconds,
                    warnings_only=not all_events,
                )
            _emit(output_csv.render_event_details(event_details), "events-details", output_dir)


# ---------------------------------------------------------------------------
# deployments command
# ---------------------------------------------------------------------------

@app.command()
def deployments(
    namespace: Annotated[Optional[str], typer.Option(
        "--namespace", "-n", help="Limit to one namespace")] = None,
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Optional[Path], typer.Option(
        "--output-dir")] = None,
) -> None:
    """Workload health for Deployments, StatefulSets and DaemonSets with pod and container detail."""
    _bootstrap()

    namespaces = kubectl.get_namespaces()
    ns_names = [namespace] if namespace else [ns.name for ns in namespaces]

    with console.status("Collecting workload health…"):
        workloads = kubectl_deployments.get_workload_health(ns_names)

    if output == OutputFormat.table:
        console.print(output_table.render_workload_health(workloads))
        console.print(output_table.render_workload_containers(workloads))
    else:
        _emit(output_csv.render_workloads(workloads), "workloads", output_dir)
        _emit(output_csv.render_workload_containers(workloads),
              "workload-containers", output_dir)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app()


if __name__ == "__main__":
    main()
