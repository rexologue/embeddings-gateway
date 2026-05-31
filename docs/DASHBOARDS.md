# Dashboards

Grafana is not included in the compose stacks. Dashboard JSON exports live in
`observability/dashboards/` and are intended for import into an existing Grafana
or managed observability workspace.

## Files

`backend-vllm-embeddings-prometheus.json`

- Uses the backend Prometheus from `deploy/embeddings`.
- Based on the vLLM Prometheus dashboard shape, trimmed for embeddings.
- Omits DCGM, node exporter, generation tokens, TTFT, decode latency, and
  inter-token latency panels.

`gateway-prometheus-overview.json`

- Uses the gateway Prometheus from `deploy/gateway`.
- Shows gateway RPS, errors, latency percentiles, body sizes, input item counts,
  and Loki publisher health.

`gateway-loki-events.json`

- Uses Loki from `deploy/gateway`.
- Shows request, response, and error events.
- Events do not include input texts.

## Datasource Variables

On import, select matching datasources:

- `DS_PROMETHEUS` for backend or gateway Prometheus dashboards;
- `DS_LOKI` for the gateway Loki dashboard.
