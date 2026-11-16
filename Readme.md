

### Code Setup

```bash
# first setup
uv init --bare .
uv add flask requests opentelemetry-distro opentelemetry-exporter-otlp
uv add opentelemetry-instrumentation-flask opentelemetry-instrumentation-requests

# just sync
uv sync

# start the app
OTEL_SERVICE_NAME=otel-tutorial \
OTEL_TRACES_EXPORTER=console \
OTEL_METRICS_EXPORTER=none \
OTEL_LOGS_EXPORTER=none \
uv run opentelemetry-instrument python app.py
```
### Otel SDK Setup

* OTEL_SERVICE_NAME	Names your service. This is the label you’ll select in Jaeger. Without it you get unknown_service.
* OTEL_TRACES_EXPORTER	Where traces go. console prints to the terminal, otlp sends to a backend, none disables.
* OTEL_METRICS_EXPORTER	Same, for metrics.
* OTEL_LOGS_EXPORTER	Same, for logs.


### Traces: app → OTLP → Jaeger

`curl http://localhost:8080/` will return a 200 response and generate a [trace](https://opentelemetry.io/docs/concepts/signals/traces/), or `for i in {1..5}; do curl -s localhost:8080; done` to generate multiple traces.

```bash
# start Jaeger 
docker run --rm --name jaeger -p 16686:16686 -p 4317:4317 -p 4318:4318 jaegertracing/all-in-one:latest

# Then run the app with 
# OTEL_TRACES_EXPORTER set to otlp and 
# OTEL_EXPORTER_OTLP_ENDPOINT set to the Jaeger endpoint.


OTEL_SERVICE_NAME=otel-tutorial \
OTEL_TRACES_EXPORTER=otlp \
OTEL_METRICS_EXPORTER=none \
OTEL_LOGS_EXPORTER=none \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
uv run opentelemetry-instrument python app.py

# or HTTP instead of gRPC
OTEL_SERVICE_NAME=otel-tutorial \
OTEL_TRACES_EXPORTER=otlp \
OTEL_METRICS_EXPORTER=none \
OTEL_LOGS_EXPORTER=none \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
uv run opentelemetry-instrument python app.py
```
Go to [jaeger](http://localhost:16686/) and select `otel-tutorial` (the service name you set in OTEL_SERVICE_NAME) to view traces.

OTel `opentelemetry-instrument` bootstrapped the SDK and turned the app’s behavior into standardized, portable data without you writing any tracing code.

---

### Metrics: app → OTLP → Prometheus

```bash
# start Prometheus
# using --web.enable-otlp-receiver Push (OTLP): the app sends metrics to Prometheus’s OTLP receiver. No scrape config needed
docker run --rm -p 9090:9090 prom/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --web.enable-otlp-receiver

# Then run the app with
# traces going to Jaeger (gRPC) and
# metrics going to Prometheus (HTTP)
OTEL_SERVICE_NAME=otel-tutorial \
OTEL_TRACES_EXPORTER=otlp \
OTEL_METRICS_EXPORTER=otlp \
OTEL_LOGS_EXPORTER=none \
OTEL_METRIC_EXPORT_INTERVAL=5000 \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://localhost:9090/api/v1/otlp/v1/metrics \
OTEL_EXPORTER_OTLP_METRICS_PROTOCOL=http/protobuf \
uv run opentelemetry-instrument python app.py
```

Then go to [Prometheus](http://localhost:9090/) and run the query `http_server_duration_milliseconds_count` to see metrics.