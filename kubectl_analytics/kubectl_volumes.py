"""Kubernetes data collection — PersistentVolumes and PVCs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from kubernetes import client
from kubernetes.client import V1PersistentVolumeClaimList, V1PersistentVolumeList
from kubernetes.client.rest import ApiException


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class VolumeStat:
    namespace: str
    pvc_count: int
    bound: int
    pending: int
    requested_gib: float
    capacity_gib: float


@dataclass
class PVSummary:
    total_pvs: int
    total_capacity_gib: float
    bound_pvs: int
    available_pvs: int
    available_gib: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STORAGE_SUFFIXES: dict[str, int] = {
    "Pi": 1024**5, "Ti": 1024**4, "Gi": 1024**3, "Mi": 1024**2, "Ki": 1024,
    "P": 1000**5,  "T": 1000**4,  "G": 1000**3,  "M": 1000**2,  "K": 1000,
}


def _parse_gib(quantity: str | None) -> float:
    if not quantity:
        return 0.0
    for suffix, multiplier in _STORAGE_SUFFIXES.items():
        if quantity.endswith(suffix):
            return float(quantity[: -len(suffix)]) * multiplier / (1024**3)
    return float(quantity) / (1024**3)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_volume_stats(namespace_names: list[str]) -> tuple[list[VolumeStat], PVSummary]:
    v1 = client.CoreV1Api()
    stats: list[VolumeStat] = []

    for ns in namespace_names:
        try:
            pvcs = (cast(V1PersistentVolumeClaimList,
                         v1.list_namespaced_persistent_volume_claim(namespace=ns)).items or [])
        except ApiException:
            continue

        bound_pvcs   = [p for p in pvcs if p.status.phase == "Bound"]
        pending_pvcs = [p for p in pvcs if p.status.phase == "Pending"]

        requested_gib = sum(
            _parse_gib(p.spec.resources.requests.get("storage"))
            for p in pvcs
            if p.spec.resources and p.spec.resources.requests
        )
        capacity_gib = sum(
            _parse_gib(p.status.capacity.get("storage"))
            for p in bound_pvcs
            if p.status.capacity
        )

        stats.append(VolumeStat(
            namespace=ns,
            pvc_count=len(pvcs),
            bound=len(bound_pvcs),
            pending=len(pending_pvcs),
            requested_gib=requested_gib,
            capacity_gib=capacity_gib,
        ))

    try:
        pvs = (cast(V1PersistentVolumeList, v1.list_persistent_volume()).items or [])
    except ApiException:
        pvs = []

    def _pv_gib(pv: Any) -> float:
        cap = getattr(pv.spec, "capacity", None) or {}
        return _parse_gib(cap.get("storage"))

    available_pvs = [pv for pv in pvs if pv.status.phase == "Available"]

    summary = PVSummary(
        total_pvs=len(pvs),
        total_capacity_gib=sum(_pv_gib(pv) for pv in pvs),
        bound_pvs=sum(1 for pv in pvs if pv.status.phase == "Bound"),
        available_pvs=len(available_pvs),
        available_gib=sum(_pv_gib(pv) for pv in available_pvs),
    )

    return stats, summary
