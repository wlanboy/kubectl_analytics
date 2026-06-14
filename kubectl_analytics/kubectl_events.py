"""Kubernetes data collection — event warnings and failure patterns."""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from kubernetes import client
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class EventNamespaceStat:
    namespace: str
    total_events: int
    warning_count: int
    top_reasons: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class EventDetail:
    namespace: str
    object_kind: str
    object_name: str
    reason: str
    message: str
    count: int
    component: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_TOP_N = 5


def _cutoff(since_seconds: int | None) -> datetime | None:
    if since_seconds is None:
        return None
    return datetime.now(timezone.utc) - timedelta(seconds=since_seconds)


def _after_cutoff(event: object, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    ts = getattr(event, "last_timestamp", None) or getattr(event, "event_time", None)
    if ts is None:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts >= cutoff


def get_event_stats(
    namespace_names: list[str],
    *,
    since_seconds: int | None = None,
) -> list[EventNamespaceStat]:
    v1 = client.CoreV1Api()
    cutoff = _cutoff(since_seconds)
    stats: list[EventNamespaceStat] = []

    for ns in namespace_names:
        try:
            events: list = getattr(v1.list_namespaced_event(namespace=ns), "items", None) or []
        except ApiException as e:
            logger.warning("Cannot list events in %s: %s", ns, e)
            continue

        events = [e for e in events if _after_cutoff(e, cutoff)]
        warning_events = [e for e in events if e.type == "Warning"]

        total = len(events)
        warning_count = len(warning_events)

        reason_counter: Counter[str] = Counter()
        for e in warning_events:
            if e.reason:
                occurrence = e.count or 1
                reason_counter[e.reason] += occurrence

        stats.append(EventNamespaceStat(
            namespace=ns,
            total_events=total,
            warning_count=warning_count,
            top_reasons=reason_counter.most_common(_TOP_N),
        ))

    return stats


def get_event_details(
    namespace_names: list[str],
    *,
    warnings_only: bool = True,
    since_seconds: int | None = None,
) -> list[EventDetail]:
    v1 = client.CoreV1Api()
    cutoff = _cutoff(since_seconds)
    details: list[EventDetail] = []

    for ns in namespace_names:
        try:
            events: list = getattr(v1.list_namespaced_event(namespace=ns), "items", None) or []
        except ApiException as e:
            logger.warning("Cannot list events in %s: %s", ns, e)
            continue

        for e in events:
            if warnings_only and e.type != "Warning":
                continue
            if not _after_cutoff(e, cutoff):
                continue
            details.append(EventDetail(
                namespace=ns,
                object_kind=e.involved_object.kind or "",
                object_name=e.involved_object.name or "",
                reason=e.reason or "",
                message=(e.message or "")[:120],
                count=e.count or 1,
                component=(e.source.component if e.source else "") or "",
            ))

    details.sort(key=lambda d: d.count, reverse=True)
    return details
