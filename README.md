# kubectl analytics

kubectl_analytics is a lightweight tool that analyzes Kubernetes logs, events, and resource states to provide actionable insights into cluster behavior.
It helps identify patterns, anomalies, and potential issues by aggregating and interpreting data directly from the Kubernetes API.

The tool focuses on fast, local analytics without requiring external services or complex observability stacks.
It is ideal for debugging, troubleshooting, and gaining a deeper understanding of what is happening inside your cluster.

Key capabilities include:

- Collecting and analyzing pod logs
- Highlighting anomalies or repeating error messages
- Inspecting Kubernetes events to detect warnings and failure patterns
- Summarizing resource states across namespaces
- Providing human‑readable diagnostics for faster troubleshooting

This makes kubectl_analytics a practical companion for:

- Developers debugging workloads
- Platform engineers analyzing cluster health
- SREs investigating incidents

Anyone who wants quick insights without deploying a full observability stack.

---

## Commands

### `kubectl-analytics crds`

CRD adoption rate — how many instances of each CRD exist across which namespaces.

```bash
uv run kubectl-analytics crds --breakdown
```

```
kubectl-analytics crds [--namespace NS] [--breakdown] [--output table|csv] [--output-dir DIR]
```

Output (`--output table`):

```
                 Custom Resource Adoption
 CRD                                         NAMESPACES  INSTANCES  ADOPTION
 certificates.cert-manager.io               12 / 24      42         50%
 issuers.cert-manager.io                     8 / 24      18         33%
 helmreleases.helm.toolkit.fluxcd.io        19 / 24      91         79%
 kustomizations.kustomize.toolkit.fluxcd.io 14 / 24      34         58%
 backupschedules.velero.io                   2 / 24       5          8%
```

With `--breakdown`, a second table shows the raw instance count per namespace × CRD:

```
          CRD Instances per Namespace
 NAMESPACE    certificates  issuers  helmreleases  backupschedules
 team-alpha   3             1        5             1
 team-beta    0             0        2             0
 platform     8             6        12            4
```

---

### `kubectl-analytics istio`

Istio service mesh usage. Without flags, shows namespace enrollment. Flags can be combined.

```bash
uv run kubectl-analytics istio

#all
uv run kubectl-analytics istio --traffic --external --policies
```

```
kubectl-analytics istio [--traffic] [--external] [--policies]
                        [--namespace NS] [--output table|csv] [--output-dir DIR]
```

**Enrollment** (default):

```
           Istio Namespace Enrollment
 NAMESPACE    INJECTION  SIDECARS  PODS  COVERAGE
 team-alpha   yes        8         8     100%
 team-beta    no         0         5       0%
 platform     yes        12        14     85%
 legacy       no         0         3       0%
```

- `INJECTION` — value of the `istio-injection` label on the namespace
- `SIDECARS` — pods with an `istio-proxy` container running
- `COVERAGE` — `sidecars / pods`

**`--traffic`** — VirtualServices, DestinationRules, Gateways, ServiceEntries, WorkloadEntries per namespace:

```bash
uv run kubectl-analytics istio --traffic
```

```
        Istio Traffic Policies per Namespace
 NAMESPACE    VirtualServices  DestinationRules  Gateways  ServiceEntries  WorkloadEntries
 team-alpha   4                2                 0         1               0
 platform     9                6                 2         3               2
 team-beta    0                0                 0         0               0
```

VirtualServices define routing rules (retries, timeouts, traffic splits). A namespace with Deployments but no VirtualServices relies on plain Kubernetes Service routing.

**`--external`** — ServiceEntries detail view (external services registered in the mesh):

```bash
uv run kubectl-analytics istio --external
```

```
          Istio External Services (ServiceEntries)
 NAMESPACE  NAME              HOSTS                            RESOLUTION  PORTS
 platform   stripe-api        api.stripe.com                   DNS         443/HTTPS
 platform   internal-pg       postgresql.internal.example.com  DNS         5432/TCP
 team-alpha legacy-erp        legacy-erp.corp                  STATIC      8080/HTTP
```

ServiceEntries register external services into the mesh — databases, third-party APIs, legacy systems. Namespaces calling external hosts without a ServiceEntry bypass all mesh policies for that traffic.

**`--policies`** — PeerAuthentication and AuthorizationPolicies per namespace:

```bash
uv run kubectl-analytics istio --policies
```

```
       Istio Security Policies per Namespace
 NAMESPACE    PeerAuthentication  AuthorizationPolicies  mTLS-MODE
 team-alpha   1                   3                      STRICT
 platform     1                   8                      STRICT
 team-beta    0                   0                      none
```

---

### `kubectl-analytics logs`

Collect and analyze pod logs per namespace — counts ERROR/WARN lines and surfaces the most common error patterns.

```bash
uv run kubectl-analytics logs --namespace mysql-replica --tail 100

# Show error-pattern breakdown in a second table
uv run kubectl-analytics logs --errors

# Only logs from the last 30 minutes
uv run kubectl-analytics logs --since 30m --errors
```

```
kubectl-analytics logs [--namespace NS] [--tail N] [--since DURATION]
                       [--errors] [--output table|csv] [--output-dir DIR]
```

Output (`--output table`):

```
            Pod Log Analysis
 NAMESPACE    POD               CONTAINER  LINES  ERRORS  WARNINGS  TOP ERROR PATTERN
 team-alpha   api-abc-xyz       api        1000   12      3         connection refused to …:…
 team-alpha   worker-def-456    worker     500    0       1         -
 team-beta    db-pod-ghi-789    postgres   200    0       0         -
```

With `--errors`, a second table shows the top error patterns per pod:

```
           Log Error Patterns
 NAMESPACE    POD              CONTAINER  COUNT  PATTERN
 team-alpha   api-abc-xyz      api        8      ERROR connection refused to …:…
 team-alpha   api-abc-xyz      api        4      ERROR timeout waiting for …
```

| Flag | Default | Description |
|---|---|---|
| `--tail N` | `100` | Lines fetched per container via the Kubernetes logs API |
| `--since DURATION` | — | Return only lines newer than the given window (`5m`, `1h`, `2d`, …) |
| `--errors` | off | Show per-pod error pattern breakdown table |

> Log lines are classified as errors when they contain `ERROR`, `FATAL`, `CRITICAL`, `EXCEPTION`, or `SEVERE`.
> Warnings are lines containing `WARN` or `WARNING`.
> Pattern grouping strips UUIDs, IP addresses, timestamps, and bare numbers so similar messages cluster together.

---

### `kubectl-analytics events`

Inspect Kubernetes events to detect warnings and failure patterns — shows a per-namespace summary of Warning events and their most common reasons. Use `--details` for the full event breakdown sorted by occurrence count.

```bash
uv run kubectl-analytics events

# Only events from the last 30 minutes
uv run kubectl-analytics events --since 30m

# Scope to one namespace and show individual events
uv run kubectl-analytics events --namespace team-alpha --since 1h --details
```

```
kubectl-analytics events [--namespace NS] [--since DURATION] [--details]
                         [--output table|csv] [--output-dir DIR]
```

Output (`--output table`):

```
        Kubernetes Event Warnings per Namespace
 NAMESPACE    TOTAL  WARNINGS  TOP REASONS
 team-alpha   42     8         BackOff×5, FailedScheduling×2, OOMKilling×1
 team-beta    15     0         -
 platform     67     21        BackOff×12, Unhealthy×6, FailedMount×3
```

With `--details`, a second table lists each warning event individually:

```
                   Kubernetes Warning Event Details
 NAMESPACE    KIND  OBJECT           REASON            COUNT  COMPONENT  MESSAGE
 platform     Pod   api-abc-xyz      BackOff           12     kubelet    Back-off restarting failed container…
 platform     Pod   worker-def-456   Unhealthy         6      kubelet    Liveness probe failed: …
 team-alpha   Pod   job-ghi-789      FailedScheduling  2      scheduler  0/3 nodes are available…
```

| Flag | Default | Description |
|---|---|---|
| `--since DURATION` | — | Only include events with `lastTimestamp` newer than the given window (`5m`, `1h`, `2d`, …) |
| `--details` | off | Show individual warning events sorted by count |

> Warning events are Kubernetes Events with `type: Warning`. The `count` reflects how many times the Kubernetes API reports the event has fired (i.e. `event.count`).
> `--since` filters by `lastTimestamp` client-side — the full event list is still fetched from the API.

---

### `kubectl-analytics volumes`

PersistentVolumeClaim usage per namespace — count, bound/pending state, requested and provisioned storage. Includes a cluster-level summary of all PersistentVolumes with free capacity.

```bash
uv run kubectl-analytics volumes
```

```
kubectl-analytics volumes [--namespace NS] [--output table|csv] [--output-dir DIR]
```

Output:

```
         Volume Mounts per Namespace
 NAMESPACE    PVCs  BOUND  PENDING  REQUESTED   CAPACITY
 team-alpha   3     3      0        30.0 GiB    30.0 GiB
 team-beta    1     0      1         5.0 GiB     0.0 GiB
 platform     8     8      0       160.0 GiB   160.0 GiB
```

```
     Persistent Volume Cluster Summary
 TOTAL PVs  CAPACITY     BOUND  AVAILABLE PVs  FREE
 15         250.0 GiB    12     3              50.0 GiB
```

| Column | Source |
|---|---|
| `REQUESTED` | sum of `spec.resources.requests.storage` across all PVCs in the namespace |
| `CAPACITY` | sum of `status.capacity.storage` for bound PVCs |
| `FREE` | total capacity of PVs in `Available` phase (provisioned but unclaimed) |

> Actual filesystem usage (bytes written to disk) requires metrics-server or Prometheus and is not available via the Kubernetes API.

---

### `kubectl-analytics adoption`

Per-namespace adoption metrics — raw counts for key platform capabilities.

```
kubectl-analytics adoption [--namespace NS] [--output table|csv] [--output-dir DIR]
```

Output:

```
             Adoption Rate per Namespace
 NAMESPACE    PODS  LIMITS  NETPOL  DEPLOYS  PDB  HPA  FLUX  ARGO
 team-alpha   8     8/8     yes     3        1    1    5     0
 team-beta    5     2/5     no      2        0    0    2     0
 platform     14    14/14   yes     7        4    3    12    0
```

| Column | Source |
|---|---|
| `LIMITS` | pods with both CPU and memory limits set (`pods_with_limits / pod_count`) |
| `NETPOL` | at least one `NetworkPolicy` in the namespace |
| `PDB` | count of `PodDisruptionBudgets` |
| `HPA` | count of `HorizontalPodAutoscalers` targeting a Deployment |
| `FLUX` | sum of `HelmReleases` + `Kustomizations` (all API versions) |
| `ARGO` | count of ArgoCD `Applications` |


## Output Formats

All commands support `--output table|csv`.

- **table** (default) — rendered to the terminal with Rich
- **csv** — one row per resource; streamed to stdout or written to `--output-dir`

```bash
# stream CSV to stdout
kubectl-analytics istio --external --output csv > external-services.csv

# write to directory
kubectl-analytics crds --output csv --output-dir ./out/
```

---

## Design Goals

- **Read-only** — only Kubernetes API reads, no cluster mutations
- **No cluster-side components** — runs client-side, requires only `kubeconfig` access
- **Per namespace by default** — every view is namespaced; cluster-wide rollups are additive
- **Graceful degradation** — missing CRDs (Istio, Flux, ArgoCD not installed) return 0, never crash

---

## Requirements

- Python >= 3.12
- Valid `kubeconfig` (or in-cluster service account)

---

## Installation

### Als globales CLI-Tool (empfohlen)

```bash
# Wheel bauen
uv build

# Global installieren — danach steht kubectl-analytics systemweit bereit
uv tool install dist/kubectl_analytics-0.1.0-py3-none-any.whl

kubectl-analytics --help

# Neu installieren nach einem Build
uv tool install --force dist/kubectl_analytics-0.1.0-py3-none-any.whl

# Deinstallieren
uv tool uninstall kubectl-analytics
```

### Als Abhängigkeit in einem anderen Projekt

```bash
uv add dist/kubectl_analytics-0.1.0-py3-none-any.whl
```

### Lokal ohne Installation testen

```bash
uv run --with dist/kubectl_analytics-0.1.0-py3-none-any.whl kubectl-analytics --help
```

---

## Development

```bash
# Abhängigkeiten inkl. Dev-Tools installieren
uv sync

# Typ-Prüfung
uv run pyright

# Linting
uv run ruff check

# Direkt aus dem Quellverzeichnis starten (ohne Build)
uv run python -m kubectl_analytics.main --help

# Wheel bauen
uv build
# Ergebnis: dist/kubectl_analytics-0.1.0-py3-none-any.whl
#           dist/kubectl_analytics-0.1.0.tar.gz
```
