# Optional local observability stack

This overlay is intentionally separate from the Python application package.
It adds Prometheus, Grafana, Tempo, Loki, and an OpenTelemetry Collector
without making any of them required for application startup.

Start the existing local dependencies first, then run from the repository
root:

```bash
docker compose -f infra/docker-compose.yml \
  -f infra/observability/docker-compose.observability.yml \
  --profile observability up
```

Run the API with `METRICS_ENABLED=true` and `METRICS_PUBLIC=true` for local
Prometheus scraping. Set `OTLP_ENDPOINT=http://localhost:4317` to export
traces through the collector. The default Grafana URL is
`http://localhost:3000`; all services bind to loopback ports.

The overlay is a developer baseline, not a production deployment. Production
retention, authentication, TLS, alert routing, and log shipping must be
configured by the deployment platform.
