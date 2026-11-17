# Kubernetes deployment

Runs the full stack from the "Collector + Loki + Grafana" stage on a vanilla Kubernetes cluster, in a single `otel-tutorial` namespace:

```
otel-app ──OTLP gRPC :4317──► otel-collector ──► jaeger:4317            (traces)
                                              ├─► prometheus:9090/api/v1/otlp (metrics)
                                              └─► loki:3100/otlp          (logs)
                                   grafana ──► loki, prometheus, jaeger   (UI)
```

All Services are `ClusterIP`. Nothing is exposed outside the cluster; use `kubectl port-forward` to reach the UIs. If you ever expose them, put them behind Cloudflare Zero Trust as required by org policy.

| File | What it deploys |
|---|---|
| `00-namespace.yaml` | `otel-tutorial` namespace |
| `app.yaml` | `dejanualex/otel-app:1.0` + Service on 8080; `OTEL_*` env points every signal at the collector |
| `otel-collector.yaml` | Collector config (ConfigMap), Deployment, Service on 4317/4318 |
| `jaeger.yaml` | `jaegertracing/all-in-one:latest`, UI 16686, OTLP 4317/4318 |
| `prometheus.yaml` | `prom/prometheus:latest` with `--web.enable-otlp-receiver`, 9090 |
| `loki.yaml` | `grafana/loki:3.4.2` single binary, 3100 |
| `grafana.yaml` | `grafana/grafana:latest` with Loki/Prometheus/Jaeger datasources provisioned, 3000 |

## Deploy

```bash
# the 00- prefix makes the namespace apply first
kubectl apply -f k8s_resources/

kubectl -n otel-tutorial get pods -w     # wait until all are Running/Ready
```

The order doesn't matter beyond the namespace. The OTel SDK and collector retry exports until the backends are up.

The image must be pullable by the cluster. `dejanualex/otel-app:1.0` is on Docker Hub. To build and push a new version from the repo root:

```bash
docker build -t dejanualex/otel-app:1.0 .
docker push dejanualex/otel-app:1.0
# on an ARM laptop pushing for x86 nodes: docker buildx build --platform linux/amd64 -t dejanualex/otel-app:1.0 --push .
```

## Generate traffic

```bash
kubectl -n otel-tutorial port-forward svc/otel-app 8080:8080
for i in {1..5}; do curl -s localhost:8080; echo; done
```

The app calls `https://httpstatus.io`, so pods need outbound internet access. If the cluster blocks egress, requests will fail but still produce error spans.

## Look at the data

```bash
kubectl -n otel-tutorial port-forward svc/jaeger 16686:16686      # http://localhost:16686  → service "otel-tutorial"
kubectl -n otel-tutorial port-forward svc/prometheus 9090:9090    # http://localhost:9090   → http_server_duration_milliseconds_count
kubectl -n otel-tutorial port-forward svc/grafana 3000:3000       # http://localhost:3000   → admin/admin
```

The datasources are already set up in Grafana. In Explore → Loki, run:

```
{service_name="otel-tutorial"} |= `text_filter`
```

The collector's `debug` exporter prints a line per batch of traces and logs:

```bash
kubectl -n otel-tutorial logs deploy/otel-collector -f
```

## Differences from the docker-compose setup

- The Loki exporter targets `http://loki:3100/otlp` instead of `host.docker.internal`.
- The app talks to `http://otel-collector:4317`, not `localhost`.
- Grafana uses its default login instead of anonymous Admin, and the datasources are provisioned rather than added by hand.
- The app gets `k8s.pod.name` and `k8s.namespace.name` resource attributes through `OTEL_RESOURCE_ATTRIBUTES`.
- Every backend stores data in memory or an `emptyDir`, so the data is lost when a pod restarts. That's fine for the tutorial but not for anything beyond it.

## Tear down

```bash
kubectl delete -f k8s_resources/      # or: kubectl delete namespace otel-tutorial
```
