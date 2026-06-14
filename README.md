# kubectl analytics

kubectl_analytics is a lightweight tool that analyzes Kubernetes logs, events, and resource states to provide actionable insights into cluster behavior.
It helps identify patterns, anomalies, and potential issues by aggregating and interpreting data directly from the Kubernetes API.

The tool focuses on fast, local analytics without requiring external services or complex observability stacks.
It is ideal for debugging, troubleshooting, and gaining a deeper understanding of what is happening inside your cluster.

Key capabilities include:

- Collecting and analyzing pod logs
- Inspecting Kubernetes events to detect warnings and failure patterns
- Summarizing resource states across namespaces
- Highlighting anomalies or repeating error messages
- Providing human‑readable diagnostics for faster troubleshooting

This makes kubectl_analytics a practical companion for:

- Developers debugging workloads
- Platform engineers analyzing cluster health
- SREs investigating incidents

Anyone who wants quick insights without deploying a full observability stack

---

## Commands

### `kubectl-analytics crds`

CRD adoption rate — how many instances of each CRD exist across which namespaces.

```bash
uv run kubectl-analytics crds
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
