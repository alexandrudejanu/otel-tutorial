# Demo evolution

The demo shows that one unchanged Flask app can emit traces, metrics, and logs through OpenTelemetry, and that the destination can change through environment variables and the process listening on port 4317. `app.py` never imports OpenTelemetry. `opentelemetry-instrument` monkey-patches Flask and `requests` at startup.

Each stage adds one idea.

1. **Console.** Traces print in the terminal. This proves the agent is producing spans before any backend exists. Metrics and logs are off.

2. **Jaeger.** `OTEL_TRACES_EXPORTER` switches from `console` to `otlp`, and `OTEL_EXPORTER_OTLP_ENDPOINT` points at Jaeger's own receiver on `:4317`. A request to `/` becomes a trace you can open in the Jaeger UI. The second command shows the same export over HTTP on `:4318` instead of gRPC.

3. **Prometheus, with Jaeger still receiving traces.** Metrics turn on. Because Prometheus does not speak OTLP gRPC on `:4317`, the app keeps traces on the shared endpoint and overrides only metrics: `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` and `OTEL_EXPORTER_OTLP_METRICS_PROTOCOL`. This is the "one app, two backends" stage, and the app has to know both addresses.

4. **Collector.** The app's variables get simpler. Both signals go to `localhost:4317`, which is now the collector. `otel-collector-config.yaml` is what forwards traces to Jaeger and metrics to Prometheus. The point of this stage is that backends can change without the app learning their URLs.

5. **Loki and Grafana.** Logs turn on with `OTEL_LOGS_EXPORTER=otlp` and the two `OTEL_PYTHON_LOGGING_*` variables. They take the same single hop to the collector, which adds a logs pipeline to Loki. Grafana is only the UI. The query `{service_name="otel-tutorial"} |= `text_filter`` reads the stream for this service and keeps lines that contain that string.

The arc: see the data, send one signal to one backend, send two signals to two backends, put a collector in front so the app has a single destination, then add the third signal without touching that destination.
