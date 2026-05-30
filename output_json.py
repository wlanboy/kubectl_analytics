"""JSON serialization of report data."""
from __future__ import annotations

import json
from dataclasses import asdict

from kubectl import AdoptionStat, CRDStat, IstioNamespaceStat, ServiceEntryStat


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def render_crds(stats: list[CRDStat]) -> str:
    return _dump([asdict(s) for s in stats])


def render_adoption(stats: list[AdoptionStat]) -> str:
    return _dump([asdict(s) for s in stats])


def render_istio(stats: list[IstioNamespaceStat]) -> str:
    return _dump([asdict(s) for s in stats])


def render_service_entries(entries: list[ServiceEntryStat]) -> str:
    return _dump([asdict(e) for e in entries])


def render_all(
    crds: list[CRDStat],
    adoption: list[AdoptionStat],
    istio: list[IstioNamespaceStat],
    service_entries: list[ServiceEntryStat],
) -> str:
    return _dump({
        "crds": [asdict(s) for s in crds],
        "adoption": [asdict(s) for s in adoption],
        "istio": [asdict(s) for s in istio],
        "service_entries": [asdict(e) for e in service_entries],
    })
