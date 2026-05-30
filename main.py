"""kubectl analytics — TUI entry point."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule

import kubectl
import output_csv
import output_json
import output_table

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
    json = "json"
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


def _emit(content: str, fmt: OutputFormat, name: str,
          output_dir: Optional[Path]) -> None:
    """Write CSV/JSON content to a file (output_dir set) or stdout."""
    if output_dir and fmt != OutputFormat.table:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{name}.{fmt.value}"
        path.write_text(content, encoding="utf-8")
    else:
        print(content, end="")


def _render(data, fmt: OutputFormat, name: str, output_dir: Optional[Path],
            table_fn, json_fn, csv_fn) -> None:
    if fmt == OutputFormat.table:
        console.print(table_fn(data))
    elif fmt == OutputFormat.json:
        _emit(json_fn(data), fmt, name, output_dir)
    else:
        _emit(csv_fn(data), fmt, name, output_dir)


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
    elif output == OutputFormat.json:
        _emit(output_json.render_crds(stats), output, "crds", output_dir)
    else:
        _emit(output_csv.render_crds(stats, total), output, "crds", output_dir)


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
        output_json.render_adoption,
        lambda s: output_csv.render_adoption(s),
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
        stats = kubectl.get_istio_stats(namespaces)

    # Default: show enrollment when no specific flag is given
    show_enrollment = not any([traffic, external, policies])

    if show_enrollment:
        _render(
            stats, output, "istio", output_dir,
            output_table.render_istio,
            output_json.render_istio,
            output_csv.render_istio,
        )

    if traffic:
        _render(
            stats, output, "istio-traffic", output_dir,
            output_table.render_istio_traffic,
            output_json.render_istio,
            output_csv.render_istio,
        )

    if policies:
        _render(
            stats, output, "istio-policies", output_dir,
            output_table.render_istio_policies,
            output_json.render_istio,
            output_csv.render_istio,
        )

    if external:
        ns_names = [ns.name for ns in namespaces]
        with console.status("Collecting ServiceEntries…"):
            entries = kubectl.get_service_entries(ns_names)
        _render(
            entries, output, "istio-external", output_dir,
            output_table.render_service_entries,
            output_json.render_service_entries,
            output_csv.render_service_entries,
        )


# ---------------------------------------------------------------------------
# all command
# ---------------------------------------------------------------------------

@app.command(name="all")
def run_all(
    output: Annotated[OutputFormat, typer.Option(
        "--output", "-o")] = OutputFormat.table,
    output_dir: Annotated[Optional[Path], typer.Option(
        "--output-dir")] = None,
) -> None:
    """Run all reports sequentially."""
    _bootstrap()

    namespaces = kubectl.get_namespaces()
    ns_names = [ns.name for ns in namespaces]
    total_ns = len(ns_names)

    console.print(Panel(
        f"[bold]kubectl analytics[/bold] — all reports\n"
        f"Namespaces: [cyan]{total_ns}[/cyan]  "
        f"Output: [cyan]{output.value}[/cyan]"
        + (f"  Dir: [cyan]{output_dir}[/cyan]" if output_dir else ""),
        expand=False,
    ))

    # --- Collect all data with a progress display ---
    results: dict = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:

        def collect(label: str, key: str, fn, *args):
            tid = progress.add_task(f"[dim]{label}[/dim]", total=None)
            data = fn(*args)
            progress.update(tid, description=f"[green]✓[/green] {label}")
            progress.stop_task(tid)
            results[key] = data

        collect("[1/4] CRD statistics",     "crds",    kubectl.get_crd_stats, ns_names)
        collect("[2/4] Adoption metrics",   "adoption", kubectl.get_adoption_stats, ns_names)
        collect("[3/4] Istio stats",        "istio",   kubectl.get_istio_stats, namespaces)
        collect("[4/4] Service entries",    "entries", kubectl.get_service_entries, ns_names)

    crd_stats     = results["crds"]
    adoption_stats = results["adoption"]
    istio_stats   = results["istio"]
    entries       = results["entries"]

    # --- Render ---
    if output == OutputFormat.table:
        _table_all(crd_stats, total_ns, adoption_stats, istio_stats, entries)

    elif output == OutputFormat.json:
        content = output_json.render_all(crd_stats, adoption_stats, istio_stats, entries)
        _emit(content, output, "all", output_dir)

    else:  # csv — one file per report
        if output_dir is None:
            console.print("[red]--output-dir is required for CSV output with 'all'[/red]")
            raise typer.Exit(1)
        _csv_all(crd_stats, total_ns, adoption_stats, istio_stats, entries, output_dir)

    if output_dir and output != OutputFormat.table:
        written = sorted(output_dir.glob(f"*.{output.value}"))
        console.print(f"\n[bold]Reports written to {output_dir}/[/bold]")
        for f in written:
            console.print(f"  [green]{f.name}[/green]")


def _table_all(crd_stats, total_ns, adoption_stats, istio_stats, entries) -> None:
    sections = [
        ("Custom Resource Adoption",    output_table.render_crds(crd_stats, total_ns)),
        ("Adoption Rate Metrics",       output_table.render_adoption(adoption_stats)),
        ("Istio Enrollment",            output_table.render_istio(istio_stats)),
        ("Istio Traffic Policies",      output_table.render_istio_traffic(istio_stats)),
        ("Istio Security Policies",     output_table.render_istio_policies(istio_stats)),
        ("Istio External Services",     output_table.render_service_entries(entries)),
    ]
    console.print()
    for title, table in sections:
        console.print(Rule(f"[bold]{title}[/bold]"))
        console.print(table)


def _csv_all(crd_stats, total_ns, adoption_stats, istio_stats, entries,
             output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "crds":           output_csv.render_crds(crd_stats, total_ns),
        "adoption":       output_csv.render_adoption(adoption_stats),
        "istio":          output_csv.render_istio(istio_stats),
        "istio-traffic":  output_csv.render_istio(istio_stats),
        "istio-policies": output_csv.render_istio(istio_stats),
        "istio-external": output_csv.render_service_entries(entries),
    }
    for name, content in files.items():
        (output_dir / f"{name}.csv").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app()


if __name__ == "__main__":
    main()
