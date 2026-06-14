"""Kubernetes data collection — pod log analysis."""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import cast

from kubernetes import client
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)

# Patterns that indicate error / warning severity in log lines
_ERROR_RE = re.compile(r"\b(ERROR|FATAL|CRITICAL|EXCEPTION|Exception|SEVERE)\b")
_WARN_RE = re.compile(r"\b(WARN|WARNING)\b")

# Maximum number of top-error patterns to keep per pod
_TOP_N = 5

# Words to strip when building a "pattern key" from an error line
# (removes UUIDs, IPs, port numbers, timestamps so similar lines group together)
_NOISE_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"  # UUID
    r"|\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?\b"  # IPv4[:port]
    r"|\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?\b"  # timestamp
    r"|\b\d+\b",  # bare numbers
    re.IGNORECASE,
)


def _pattern_key(line: str) -> str:
    """Return a normalised version of an error line for frequency grouping."""
    key = _NOISE_RE.sub("…", line)
    # Keep only the first 120 chars to avoid giant keys
    return key[:120].strip()


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PodLogStat:
    namespace: str
    pod: str
    container: str
    total_lines: int
    error_count: int
    warning_count: int
    top_errors: list[tuple[str, int]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_log_stats(
    namespace_names: list[str],
    *,
    tail_lines: int = 100,
    since_seconds: int | None = None,
) -> list[PodLogStat]:
    v1 = client.CoreV1Api()
    stats: list[PodLogStat] = []

    for ns in namespace_names:
        try:
            pods: list = getattr(v1.list_namespaced_pod(namespace=ns), "items", None) or []
        except ApiException as e:
            logger.warning("Cannot list pods in %s: %s", ns, e)
            continue

        for pod in pods:
            pod_name: str = cast(str, pod.metadata.name)
            containers = [c.name for c in (pod.spec.containers or [])]

            for container in containers:
                try:
                    kwargs: dict = dict(
                        namespace=ns,
                        name=pod_name,
                        container=container,
                        tail_lines=tail_lines,
                        _preload_content=True,
                    )
                    if since_seconds is not None:
                        kwargs["since_seconds"] = since_seconds

                    raw: str = cast(str, v1.read_namespaced_pod_log(**kwargs) or "")
                except ApiException as e:
                    if e.status == 400:
                        # Pod not running / container in init state — skip silently
                        continue
                    logger.warning("Cannot read logs for %s/%s[%s]: %s",
                                   ns, pod_name, container, e)
                    continue

                lines = raw.splitlines()
                error_lines = [ln for ln in lines if _ERROR_RE.search(ln)]
                warn_count = sum(1 for ln in lines if _WARN_RE.search(ln))

                counter: Counter[str] = Counter(_pattern_key(ln) for ln in error_lines)
                top_errors = counter.most_common(_TOP_N)

                stats.append(PodLogStat(
                    namespace=ns,
                    pod=pod_name,
                    container=container,
                    total_lines=len(lines),
                    error_count=len(error_lines),
                    warning_count=warn_count,
                    top_errors=top_errors,
                ))

    return stats
