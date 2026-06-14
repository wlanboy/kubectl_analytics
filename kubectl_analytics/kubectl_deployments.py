"""Kubernetes data collection — workload health: Deployments, StatefulSets, DaemonSets."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, cast

from kubernetes import client
from kubernetes.client import (
    V1DaemonSetList,
    V1DeploymentList,
    V1PodList,
    V1StatefulSetList,
)
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)

_PROBLEM_REASONS = frozenset({
    "CrashLoopBackOff", "OOMKilled", "Error", "ImagePullBackOff",
    "ErrImagePull", "CreateContainerConfigError", "RunContainerError",
    "PostStartHookError", "ContainerCannotRun",
})


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ContainerHealth:
    name: str
    restart_count: int
    state: str    # "running", "waiting", "terminated", "unknown"
    reason: str   # e.g. "CrashLoopBackOff", "OOMKilled", ""
    is_init: bool

    @property
    def is_problem(self) -> bool:
        return self.reason in _PROBLEM_REASONS


@dataclass
class PodHealth:
    name: str
    namespace: str
    phase: str    # "Running", "Pending", "Failed", "Succeeded", "Unknown"
    containers: list[ContainerHealth] = field(default_factory=list)

    @property
    def total_restarts(self) -> int:
        return sum(c.restart_count for c in self.containers)

    @property
    def problem_reason(self) -> str:
        for c in self.containers:
            if c.is_problem:
                return f"{c.name}: {c.reason}"
        return ""


@dataclass
class WorkloadHealth:
    kind: str       # "Deployment", "StatefulSet", "DaemonSet"
    name: str
    namespace: str
    desired: int
    ready: int
    unavailable: int
    pods: list[PodHealth] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return self.unavailable == 0 and self.ready >= self.desired

    @property
    def total_restarts(self) -> int:
        return sum(p.total_restarts for p in self.pods)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _selector_str(match_labels: dict[str, str] | None) -> str:
    if not match_labels:
        return ""
    return ",".join(f"{k}={v}" for k, v in match_labels.items())


def _container_health(cs: Any, *, is_init: bool) -> ContainerHealth:
    state = "unknown"
    reason = ""
    if cs.state:
        if cs.state.running:
            state = "running"
        elif cs.state.waiting:
            state = "waiting"
            reason = cs.state.waiting.reason or ""
        elif cs.state.terminated:
            state = "terminated"
            reason = cs.state.terminated.reason or ""
    return ContainerHealth(
        name=cs.name,
        restart_count=cs.restart_count or 0,
        state=state,
        reason=reason,
        is_init=is_init,
    )


def _pod_health(pod: Any, namespace: str) -> PodHealth:
    phase = (pod.status.phase or "Unknown") if pod.status else "Unknown"
    containers: list[ContainerHealth] = []

    for cs in (pod.status.init_container_statuses or []) if pod.status else []:
        containers.append(_container_health(cs, is_init=True))

    for cs in (pod.status.container_statuses or []) if pod.status else []:
        containers.append(_container_health(cs, is_init=False))

    return PodHealth(name=pod.metadata.name, namespace=namespace,
                     phase=phase, containers=containers)


def _fetch_pods(v1: client.CoreV1Api, namespace: str,
                selector: str) -> list[PodHealth]:
    if not selector:
        return []
    try:
        items = cast(V1PodList, v1.list_namespaced_pod(
            namespace=namespace, label_selector=selector
        )).items or []
        return [_pod_health(p, namespace) for p in items]
    except ApiException as e:
        logger.warning("Cannot list pods in %s (selector=%s): %s",
                       namespace, selector, e)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_workload_health(namespace_names: list[str]) -> list[WorkloadHealth]:
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    results: list[WorkloadHealth] = []

    for ns in namespace_names:
        # Deployments
        try:
            for d in (cast(V1DeploymentList, apps_v1.list_namespaced_deployment(namespace=ns)).items or []):
                st = d.status
                selector = _selector_str(
                    d.spec.selector.match_labels if d.spec.selector else None
                )
                results.append(WorkloadHealth(
                    kind="Deployment",
                    name=d.metadata.name,
                    namespace=ns,
                    desired=d.spec.replicas or 0,
                    ready=st.ready_replicas or 0,
                    unavailable=st.unavailable_replicas or 0,
                    pods=_fetch_pods(v1, ns, selector),
                ))
        except ApiException as e:
            logger.warning("Cannot list deployments in %s: %s", ns, e)

        # StatefulSets
        try:
            for s in (cast(V1StatefulSetList, apps_v1.list_namespaced_stateful_set(namespace=ns)).items or []):
                st = s.status
                desired = s.spec.replicas or 0
                ready = st.ready_replicas or 0
                selector = _selector_str(
                    s.spec.selector.match_labels if s.spec.selector else None
                )
                results.append(WorkloadHealth(
                    kind="StatefulSet",
                    name=s.metadata.name,
                    namespace=ns,
                    desired=desired,
                    ready=ready,
                    unavailable=max(0, desired - ready),
                    pods=_fetch_pods(v1, ns, selector),
                ))
        except ApiException as e:
            logger.warning("Cannot list statefulsets in %s: %s", ns, e)

        # DaemonSets
        try:
            for d in (cast(V1DaemonSetList, apps_v1.list_namespaced_daemon_set(namespace=ns)).items or []):
                st = d.status
                selector = _selector_str(
                    d.spec.selector.match_labels if d.spec.selector else None
                )
                results.append(WorkloadHealth(
                    kind="DaemonSet",
                    name=d.metadata.name,
                    namespace=ns,
                    desired=st.desired_number_scheduled or 0,
                    ready=st.number_ready or 0,
                    unavailable=st.number_unavailable or 0,
                    pods=_fetch_pods(v1, ns, selector),
                ))
        except ApiException as e:
            logger.warning("Cannot list daemonsets in %s: %s", ns, e)

    return results
