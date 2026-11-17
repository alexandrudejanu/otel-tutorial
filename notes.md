# Demo evolution

The demo shows that one unchanged Flask app can emit traces, metrics, and logs through OpenTelemetry, and that the destination can change through environment variables and the process listening on port 4317. `app.py` never imports OpenTelemetry. `opentelemetry-instrument` monkey-patches Flask and `requests` at startup.

Each stage adds one idea.

1. **Console.** Traces print in the terminal. This proves the agent is producing spans before any backend exists. Metrics and logs are off.

2. **Jaeger.** `OTEL_TRACES_EXPORTER` switches from `console` to `otlp`, and `OTEL_EXPORTER_OTLP_ENDPOINT` points at Jaeger's own receiver on `:4317`. A request to `/` becomes a trace you can open in the Jaeger UI. The second command shows the same export over HTTP on `:4318` instead of gRPC.

3. **Prometheus, with Jaeger still receiving traces.** Metrics turn on. Because Prometheus does not speak OTLP gRPC on `:4317`, the app keeps traces on the shared endpoint and overrides only metrics: `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` and `OTEL_EXPORTER_OTLP_METRICS_PROTOCOL`. This is the "one app, two backends" stage, and the app has to know both addresses.

4. **Collector.** The app's variables get simpler. Both signals go to `localhost:4317`, which is now the collector. `otel-collector-config.yaml` is what forwards traces to Jaeger and metrics to Prometheus. The point of this stage is that backends can change without the app learning their URLs.

5. **Loki and Grafana.** Logs turn on with `OTEL_LOGS_EXPORTER=otlp` and the two `OTEL_PYTHON_LOGGING_*` variables. They take the same single hop to the collector, which adds a logs pipeline to Loki. Grafana is only the UI. The query `{service_name="otel-tutorial"} |= `text_filter`` reads the stream for this service and keeps lines that contain that string.

---

## How the services communicate (stage 5)

```
                    traces + metrics + logs
┌───────────┐       OTLP gRPC :4317        ┌────────────────┐
│ Flask app │ ───────────────────────────► │ OTel Collector │
│   :8080   │                              └───────┬────────┘
└─────┬─────┘                                      │
      │ HTTPS                 ┌────────────────────┼─────────────────────┐
      ▼                       │ traces             │ metrics             │ logs
 httpstatus.io                │ OTLP gRPC :4317    │ OTLP HTTP :9090     │ OTLP HTTP :3100
                              ▼                    ▼ /api/v1/otlp        ▼ /otlp
                       ┌────────────┐       ┌────────────┐        ┌────────────┐
                       │   Jaeger   │       │ Prometheus │        │    Loki    │
                       │ UI :16686  │       │ UI :9090   │        │   :3100    │
                       └────────────┘       └────────────┘        └─────▲──────┘
                                                                        │ LogQL queries
                                                                  ┌─────┴──────┐
                                                                  │  Grafana   │
                                                                  │   :3000    │
                                                                  └────────────┘
```

The app only ever talks to the collector. The collector is the only thing that knows where the backends are. Grafana reads from Loki and doesn't receive any telemetry itself.

The arc: see the data, send one signal to one backend, send two signals to two backends, put a collector in front so the app has a single destination, then add the third signal without touching that destination.

```bash
kubectl apply -f k8s_resources/00-namespace.yaml
kubectl apply -f k8s_resources/jaeger.yaml -f k8s_resources/prometheus.yaml -f k8s_resources/loki.yaml
kubectl -n otel-tutorial wait --for=condition=available deploy/jaeger deploy/prometheus deploy/loki --timeout=120s
kubectl apply -f k8s_resources/otel-collector.yaml -f k8s_resources/grafana.yaml
kubectl -n otel-tutorial wait --for=condition=available deploy/otel-collector --timeout=60s
kubectl apply -f k8s_resources/app.yaml

# To get data without the collector, point the app straight at the backends
kubectl -n otel-tutorial set env deploy/otel-app \
    OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317 \
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://prometheus:9090/api/v1/otlp/v1/metrics \
    OTEL_EXPORTER_OTLP_METRICS_PROTOCOL=http/protobuf \
    OTEL_LOGS_EXPORTER=none

# generate traffic
kubectl -n otel-tutorial port-forward svc/otel-app 8080:8080
for i in {1..20}; do curl -s localhost:8080 >/dev/null; sleep 0.2; done

# check grafana for http_server_duration_milliseconds_count
kubectl -n otel-tutorial port-forward  services/grafana 3000:3000 
```

---

Collector as operator

Why cert-manager is needed

  The operator works through admission webhooks. When a pod is created, the Kubernetes API server calls the operator's mutating webhook. That webhook is what adds the Go eBPF sidecar and sets the OTEL_* variables. The operator also runs webhooks that check
  OpenTelemetryCollector and Instrumentation resources when you apply them.

  The API server will only call webhooks over HTTPS, and only if it trusts the webhook's certificate:

  kubectl apply go-hello Deployment
        │
        ▼
  API server ──HTTPS──► operator webhook (mutates the pod: adds the sidecar)
        │   checks the webhook's TLS cert against the caBundle
        │   stored in the MutatingWebhookConfiguration
        ▼
  pod created with the sidecar

  So the operator needs a TLS certificate, and the webhook configurations need the matching CA. The operator's release manifest doesn't create these itself. It includes cert-manager Issuer and Certificate resources, and cert-manager then:
  1. issues a self-signed certificate into a Secret that the operator mounts, and
  2. copies the CA into the webhook configurations and the CRD conversion webhook (its cainjector component does this),
  3. renews the certificate before it expires.

  Without cert-manager, applying opentelemetry-operator.yaml fails on the Issuer and Certificate resources. Even if you got past that, the API server couldn't reach the webhooks, so no sidecar would be injected.

  Doing it without cert-manager

  cert-manager is a requirement of the plain manifest install, not of the operator. The Helm chart can generate the webhook certificate itself:

  helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
  helm install opentelemetry-operator open-telemetry/opentelemetry-operator \
    -n opentelemetry-operator-system --create-namespace \
    --set admissionWebhooks.certManager.enabled=false \
    --set admissionWebhooks.autoGenerateCert.enabled=true

  The downside is that Helm creates the certificate at install and upgrade time and doesn't rotate it automatically, so it has to be renewed with a helm upgrade before it expires. cert-manager rotates it for you. For a tutorial cluster the Helm route is simpler: one
  component instead of two.
