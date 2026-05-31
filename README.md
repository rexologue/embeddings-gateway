# Embeddings Gateway

OpenAI-compatible embeddings deployment split into two small stacks:

- `deploy/embeddings` runs the vLLM embeddings backend and backend Prometheus.
- `deploy/gateway` runs the API gateway, gateway Prometheus, and Loki.

The gateway is intentionally narrow: it proxies `/v1/embeddings`, `/v1/models`,
and other `/v1/*` requests without chat/session/streaming-specific behavior.

## Layout

```text
deploy/embeddings   vLLM embeddings backend and backend Prometheus
deploy/gateway      API gateway, gateway Prometheus, Loki
gateway             FastAPI gateway source
observability       Grafana dashboard JSON exports
docs                deployment and observability notes
```

## Start Backend

```bash
cp deploy/embeddings/.env.example deploy/embeddings/.env
cd deploy/embeddings
docker compose --env-file .env -f docker-compose.yaml up -d
```

Default URLs:

- vLLM API: `http://0.0.0.0:11010`
- vLLM Prometheus: `http://0.0.0.0:11101`

## Start Gateway

```bash
cp deploy/gateway/.env.example deploy/gateway/.env
cd deploy/gateway
docker compose --env-file .env -f docker-compose.yaml up -d --build
```

Default URLs:

- gateway API: `http://0.0.0.0:11000`
- gateway health: `http://0.0.0.0:11000/health`
- gateway metrics: `http://0.0.0.0:11000/gateway/metrics`
- gateway Prometheus: `http://0.0.0.0:11100`
- Loki: `http://0.0.0.0:11102`

## Smoke Check

```bash
curl -fsS http://127.0.0.1:11000/v1/models

curl -fsS http://127.0.0.1:11000/v1/embeddings \
  -H 'content-type: application/json' \
  -d '{"model":"embeddings-model","input":["hello","world"]}'

curl -fsS http://127.0.0.1:11000/gateway/metrics
```

## Dashboards

Grafana is not part of either compose stack. Import JSON from
`observability/dashboards/` into an existing Grafana:

- `backend-vllm-embeddings-prometheus.json`
- `gateway-prometheus-overview.json`
- `gateway-loki-events.json`

See `docs/` for details.
