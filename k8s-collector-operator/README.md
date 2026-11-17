# OpenTelemetry Operator: collector + zero-code Go instrumentation

The same zero-code idea as the Python app, but done by the cluster instead of the image. `dejanualex/go-hello:1.0` is a plain Go binary (`/app/main`, port 8888). It has no OpenTelemetry SDK and no wrapper `CMD`. The OpenTelemetry Operator does two things:

1. **Runs the collector** from an `OpenTelemetryCollector` resource (`01-collector.yaml`). It replaces the hand-written ConfigMap, Deployment and Service.
2. **Instruments the app** from an `Instrumentation` resource (`02-instrumentation.yaml`) plus two pod annotations (`03-go-app.yaml`).

```
┌─────────────────────── go-hello pod (shareProcessNamespace) ───────────────────────┐
│  go-hello container          opentelemetry-auto-instrumentation sidecar (eBPF)     │
│  /app/main :8888   ◄──────── attaches uprobes to net/http in /app/main             │
└────────────────────────────────────────────┬───────────────────────────────────────┘
                                             │ OTLP HTTP :4318
                                             ▼
                                   otel-collector     ──► jaeger:4317 (traces)
                                   (operator-managed)  ──► prometheus / loki (unused by Go)
```

### How Go differs from the Python agent

Python can load an agent into the process through `sitecustomize`. A compiled Go binary can't. For Go, the operator adds a **privileged sidecar**, enables `shareProcessNamespace` on the pod, and uses **eBPF uprobes** to watch functions such as `net/http` handlers in the running binary. That's why it needs the binary's path (`otel-go-auto-target-exe`). The binary must also keep its symbols, and this one does: Go 1.21, not stripped.

## Prerequisites

- The backends and namespace from `../k8s_resources`. You don't need `otel-collector.yaml` or `app.yaml` from there.
- Linux nodes with kernel 4.19 or newer. Privileged pods must be allowed in `otel-tutorial`, because Pod Security `baseline` or `restricted` will reject the sidecar.
- cluster-admin rights. The operator installs CRDs and admission webhooks for the whole cluster.
- `helm` v3 or newer.

> Check `kubectl config current-context` before every step below. These install cluster-wide components.

### Install the operator with Helm (no cert-manager)

The API server only calls admission webhooks over HTTPS, so the operator needs a TLS certificate that the API server trusts. The plain manifest install gets one from cert-manager. With the Helm chart, Helm generates a self-signed certificate and puts its CA into the webhook configurations, so cert-manager isn't needed.

```bash
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update

helm install opentelemetry-operator open-telemetry/opentelemetry-operator \
  --version 0.129.0 \
  -n opentelemetry-operator-system --create-namespace \
  --set admissionWebhooks.certManager.enabled=false \
  --set admissionWebhooks.autoGenerateCert.enabled=true \
  --set manager.autoInstrumentation.go.enabled=true

kubectl -n opentelemetry-operator-system wait --for=condition=available deploy --all --timeout=180s
```

| Value | Why |
|---|---|
| `admissionWebhooks.certManager.enabled=false` | Don't use cert-manager. It's on by default, and the install fails without it. |
| `admissionWebhooks.autoGenerateCert.enabled=true` | Helm creates the webhook certificate and CA (valid 365 days). |
| `manager.autoInstrumentation.go.enabled=true` | Go auto-instrumentation is off by default in the operator. |
| `--version 0.129.0` | Chart pinned for reproducibility (operator `0.162.0`). |

**Certificate lifetime:** Helm doesn't rotate the certificate on its own. It generates a new one on every `helm upgrade`, through `autoGenerateCert.recreate`, which is on by default. If the cluster lives longer than a year, run `helm upgrade` before the certificate expires. Otherwise the webhooks start failing, and pods are created without instrumentation or rejected.

The chart's default collector image is `opentelemetry-collector-k8s`, which includes everything `01-collector.yaml` uses (`otlp`, `otlphttp`, `debug`, `batch`).

## Deploy

Order matters here. The operator only changes a pod when it is **created**, so the `Instrumentation` must exist before the app's pods start. The files are numbered to apply in the right order:

```bash
# backends (+ namespace) from the plain setup
kubectl apply -f k8s_resources/00-namespace.yaml \
  -f k8s_resources/jaeger.yaml -f k8s_resources/prometheus.yaml \
  -f k8s_resources/loki.yaml -f k8s_resources/grafana.yaml

# collector -> instrumentation -> app
kubectl apply -f k8s-collector-operator/
```

If the app was running before the `Instrumentation` existed, or before the operator was installed with Go enabled, recreate its pods:

```bash
kubectl -n otel-tutorial rollout restart deploy/go-hello
```

## Verify the injection

```bash
# expect two containers: go-hello and opentelemetry-auto-instrumentation
kubectl -n otel-tutorial get pod -l app=go-hello \
  -o jsonpath='{range .items[*].spec.containers[*]}{.name}{"\n"}{end}'

# sidecar logs should show it found /app/main and loaded probes
kubectl -n otel-tutorial logs deploy/go-hello -c opentelemetry-auto-instrumentation

# operator-created collector objects
kubectl -n otel-tutorial get opentelemetrycollector,instrumentation
kubectl -n otel-tutorial get svc | grep otel-collector
```

If only one container appears, check the operator logs: `kubectl -n opentelemetry-operator-system logs deploy/opentelemetry-operator`. The usual causes are Go support not being enabled (`helm get values opentelemetry-operator -n opentelemetry-operator-system`), or the `Instrumentation` being created after the pod.

## Generate traffic and look at traces

```bash
kubectl -n otel-tutorial port-forward svc/go-hello 8888:8888
for i in {1..20}; do curl -s localhost:8888/ >/dev/null; done

kubectl -n otel-tutorial port-forward svc/jaeger 16686:16686   # http://localhost:16686
```

In Jaeger, select the service **`go-hello`**. The operator names the service after the Deployment unless you set `OTEL_SERVICE_NAME`. The collector's debug output confirms that traces arrive:

```bash
kubectl -n otel-tutorial logs deploy/otel-collector -f
```

Go eBPF instrumentation produces **traces**. Don't expect `http_server_*` metrics in Prometheus or logs in Loki from this app.

## Tear down

```bash
kubectl delete -f k8s-collector-operator/
# operator (cluster-wide, only if nothing else uses it)
# This chart installs the CRDs as templates, so uninstall also deletes them, along with
# EVERY OpenTelemetryCollector / Instrumentation resource in the cluster. Run it last.
helm uninstall opentelemetry-operator -n opentelemetry-operator-system
```
