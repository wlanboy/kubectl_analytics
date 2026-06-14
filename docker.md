# Docker

## Build

```bash
docker build -t kubectl-analytics .
```

## Ausführen

Das lokale `~/.kube`-Verzeichnis (von `oc login` befüllt) wird read-only in den Container gemountet:

```bash
docker run --name kubectlanalytics --rm \
  -v ~/.kube:/root/.kube:ro \
  kubectl-analytics crds --breakdown
```

Alle Subcommands funktionieren analog:

```bash
docker run --rm -v ~/.kube:/root/.kube:ro kubectl-analytics events
docker run --rm -v ~/.kube:/root/.kube:ro kubectl-analytics logs --namespace my-ns
```

## Hinweise

- Kein `oc` im Container nötig — das Tool nutzt die Kubernetes-API direkt über das Python-SDK.
- Falls Zertifikate außerhalb von `~/.kube` liegen (z.B. Custom CA), zusätzlich mounten:
  ```bash
  -v /etc/ssl/certs:/etc/ssl/certs:ro
  ```
