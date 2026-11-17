### Overview

⚠️ Zero-code instrumentation adds the OpenTelemetry API and SDK capabilities to your application. 

Generally, you run a set of applications in production and:

    - Your goal is to get telemetry out of them without touching their code.
    - You want to collect traces, metrics, and logs from several services and send them off to your observability backend

Automatic instrumentation with Python uses a Python agent that can be attached to any Python application. This agent primarily uses **monkey patching** to modify library functions at runtime, allowing for the capture of telemetry data.

### Code Setup

```bash
# first setup
uv init --bare .
uv add flask requests opentelemetry-distro opentelemetry-exporter-otlp
uv add opentelemetry-instrumentation-flask opentelemetry-instrumentation-requests

# just sync
uv sync

# start the app vanilla
OTEL_SERVICE_NAME=otel-tutorial \
OTEL_TRACES_EXPORTER=console \
OTEL_METRICS_EXPORTER=none \
OTEL_LOGS_EXPORTER=none \
uv run opentelemetry-instrument python app.py

# start app as docker image
# exports all three signals over OTLP, so the full collector stack must be running first
docker run --rm -p 8080:8080 \
  -e OTEL_SERVICE_NAME=otel-tutorial \
  -e OTEL_TRACES_EXPORTER=otlp \
  -e OTEL_METRICS_EXPORTER=otlp \
  -e OTEL_LOGS_EXPORTER=otlp \
  -e OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true \
  -e OTEL_PYTHON_LOG_LEVEL=info \
  -e OTEL_METRIC_EXPORT_INTERVAL=5000 \
  -e OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4317 \
  dejanualex/otel-app:1.0
```

### Otel SDK Setup

| Variable | Description | Example / Common Values |
|---|---|---|
| `OTEL_SERVICE_NAME` | Sets the `service.name` resource attribute identifying the service in backends like Jaeger. Without it, defaults to `unknown_service`. | `otel-tutorial` |
| `OTEL_TRACES_EXPORTER` | Destination for collected traces. | `otlp`, `console`, `none` |
| `OTEL_METRICS_EXPORTER` | Destination for collected metrics. | `otlp`, `console`, `none` |
| `OTEL_LOGS_EXPORTER` | Destination for emitted logs. | `otlp`, `console`, `none` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Base target URL for the OTLP exporter across signals. | `http://localhost:4317` (gRPC), `http://localhost:4318` (HTTP) |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | Transport protocol for OTLP export across signals. | `grpc`, `http/protobuf` |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | Signal-specific endpoint override for exporting metrics. | `http://localhost:9090/api/v1/otlp/v1/metrics` |
| `OTEL_EXPORTER_OTLP_METRICS_PROTOCOL` | Protocol override specifically for metrics export. | `http/protobuf`, `grpc` |
| `OTEL_METRIC_EXPORT_INTERVAL` | Interval in milliseconds between metric export batches (default is `60000`). | `5000` |
| `OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED` | Enables automatic instrumentation and capture of standard Python `logging`. | `true`, `false` |
| `OTEL_PYTHON_LOG_LEVEL` | Minimum log severity level captured and exported to OpenTelemetry. | `info`, `debug`, `warning`, `error` |


### Traces: app → OTLP → Jaeger


```bash
# start Jaeger (Jaeger's own receiver on 4317)
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

`curl http://localhost:8080/` will return a 200 response and generate a [trace](https://opentelemetry.io/docs/concepts/signals/traces/), or `for i in {1..5}; do curl -s localhost:8080; done` to generate multiple traces.


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

---

### Collector: App → Collector → Jaeger (traces) + Prometheus (metrics)

* The collector is a headless service: it receives, processes, and exports data and it is configured via [otelcol-config.yml](https://github.com/open-telemetry/opentelemetry-demo/blob/main/src/otel-collector/otelcol-config.yml)

```bash
# start jaeger and prometheus as before, 
# + the collector
docker compose -f docker-compose-otel-collector.yaml up -d

# OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
# which now lands on the collector instead of Jaeger or Prometheus.
OTEL_SERVICE_NAME=otel-tutorial \
OTEL_TRACES_EXPORTER=otlp \
OTEL_METRICS_EXPORTER=otlp \
OTEL_LOGS_EXPORTER=none \
OTEL_METRIC_EXPORT_INTERVAL=5000 \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
uv run opentelemetry-instrument python app.py

# stop 
docker compose -f docker-compose-otel-collector.yaml down
```

---

### Collector: App → Collector → Jaeger (traces) + Prometheus (metrics) + Loki (logs) + Grafana (UI)

First uncomment the lines marked `toogle comment` in `otel-collector-config.yaml` (the `otlphttp/loki` exporter and the `logs` pipeline) to enable log export to Loki.

```bash
# start jaeger and prometheus, collector as before, 
# + loki and grafana
docker compose -f docker-compose-otel-collector-full.yaml up -d

OTEL_SERVICE_NAME=otel-tutorial \
OTEL_TRACES_EXPORTER=otlp \
OTEL_METRICS_EXPORTER=otlp \
OTEL_LOGS_EXPORTER=otlp \
OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true \
OTEL_PYTHON_LOG_LEVEL=info \
OTEL_METRIC_EXPORT_INTERVAL=5000 \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
uv run opentelemetry-instrument python app.py

# stop 
docker compose -f docker-compose-otel-collector-full.yaml down
```
Go to [Grafana](http://localhost:3000) and add Loki as datasource (Connections
--> Add new connection http://loki:3100) and check logs (show logs from the otel-tutorial service whose message contains text_filter):

```
# run query
# otel-tutorial stream selector
{service_name="otel-tutorial"} |= `text_filter` 
```