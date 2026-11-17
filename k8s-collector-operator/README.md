# OpenTelemetry Operator: zero-code Go instrumentation

`dejanualex/go-hello:1.0` is a plain Go binary (`/app/main`, port 8888) with no OpenTelemetry code. The OpenTelemetry Operator runs the collector and adds an **eBPF sidecar** to the app pod to trace it.

```
go-hello pod ─┬─ go-hello (/app/main :8888)
              └─ eBPF sidecar ──OTLP HTTP :4318──► otel-collector ──► jaeger (traces)
                                                                  ├─► prometheus (metrics)
                                                                  └─► loki (logs)
                                                       grafana ──► jaeger, prometheus, loki (UI)
```

The Go agent produces **traces only**. The metrics and logs pipelines are there for other workloads.

## Prerequisites

- cluster-admin rights and `helm` v3 or newer
- Linux nodes with kernel 4.19 or newer
- privileged pods allowed in `otel-tutorial`, because the eBPF sidecar runs privileged

> Run `kubectl config current-context` before you start.

## 1. Install the operator

```bash
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts && helm repo update

helm install opentelemetry-operator open-telemetry/opentelemetry-operator --version 0.129.0 \
  -n opentelemetry-operator-system --create-namespace \
  --set admissionWebhooks.certManager.enabled=false \
  --set admissionWebhooks.autoGenerateCert.enabled=true \
  --set manager.autoInstrumentation.go.enabled=true

kubectl -n opentelemetry-operator-system wait --for=condition=available deploy --all --timeout=180s
```

Helm generates the webhook TLS certificate, so cert-manager isn't needed. The certificate is valid for 365 days and is regenerated on `helm upgrade`. Go instrumentation is off by default, which is why the last `--set` is there.

## 2. Create the resources, in this order

| # | File | Creates | Why here |
|---|---|---|---|
| 0 | `00-namespace.yaml` | `otel-tutorial` namespace | Everything else lives in it |
| 1 | `01-jaeger.yaml` | Jaeger (UI 16686, OTLP 4317/4318) | Backend for traces |
| 2 | `02-prometheus.yaml` | Prometheus with the OTLP receiver (9090) | Backend for metrics |
| 3 | `03-loki.yaml` | Loki (3100) | Backend for logs |
| 4 | `04-grafana.yaml` | Grafana (3000), with all three datasources provisioned and Jaeger as the default | UI that reads the backends |
| 5 | `05-collector.yaml` | `OpenTelemetryCollector` `otel`, which becomes the `otel-collector` Service | Its exporters point at the backends |
| 6 | `06-instrumentation.yaml` | `Instrumentation`, which exports to `otel-collector:4318` | **Must exist before the app's pods** |
| 7 | `07-go-app.yaml` | `go-hello` Deployment and Service (8888), with the inject annotations | The webhook adds the sidecar when the pod is created |



```bash
# the file prefixes match this order, so one command does it
kubectl apply -f k8s-collector-operator/

# check
kubectl -n otel-tutorial get po
```

Only two steps have a hard order: the namespace first, and step 6 before step 7. The operator only changes a pod when it's created. If the app started before the `Instrumentation` existed, recreate its pods:

```bash
kubectl -n otel-tutorial rollout restart deploy/go-hello
```

## 3. Verify

```bash
# expect two containers: go-hello and opentelemetry-auto-instrumentation
kubectl -n otel-tutorial get pod -l app=go-hello -o jsonpath='{.items[*].spec.containers[*].name}'

kubectl -n otel-tutorial port-forward svc/go-hello 8888:8888 &
for i in {1..20}; do curl -s localhost:8888/ >/dev/null; done

kubectl -n otel-tutorial port-forward svc/jaeger 16686:16686   # http://localhost:16686, service "go-hello"
kubectl -n otel-tutorial port-forward svc/grafana 3000:3000    # http://localhost:3000 (admin/admin), Explore → Jaeger
```

If there's no sidecar, check `kubectl -n opentelemetry-operator-system logs deploy/opentelemetry-operator`.

## Tear down

```bash
kubectl delete -f k8s-collector-operator/
# also deletes the operator CRDs and every OpenTelemetryCollector/Instrumentation in the cluster
helm uninstall opentelemetry-operator -n opentelemetry-operator-system
```
