# Embeddings Gateway

OpenAI-compatible embeddings deployment split into two small stacks:

- `deploy/embeddings` runs the vLLM embeddings backend.
- `deploy/gateway` runs the API gateway, VictoriaMetrics (gateway and vLLM
  metrics), and Loki.

The gateway is intentionally narrow: it proxies `/v1/embeddings`, `/v1/models`,
and other `/v1/*` requests without chat/session/streaming-specific behavior.

## Layout

```text
deploy/embeddings   vLLM embeddings backend (serve_embeddings.example.sh)
deploy/gateway      API gateway, VictoriaMetrics (gateway + vLLM), Loki
gateway             FastAPI gateway source
observability       Grafana dashboard JSON exports
docs                deployment and observability notes
```

## Start Backend

```bash
cd deploy/embeddings
cp .env.example .env
cp serve_embeddings.example.sh serve_embeddings.sh
docker compose --env-file .env -f docker-compose.yaml up -d
```

`.env` holds the image, weights, GPU and port; `serve_embeddings.sh` holds the
vLLM parameters, each commented in `serve_embeddings.example.sh`. Both are
local and not in git (`docs/DEPLOY.md`).

Default URLs:

- vLLM API: `http://0.0.0.0:11010`

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
- VictoriaMetrics (Prometheus API, vmui at `/vmui`): `http://0.0.0.0:11100`
- Loki: `http://0.0.0.0:11102`

## Keys

There are two keys, and a caller only ever sees one:

- `GATEWAY_API_KEYS` (`deploy/gateway/.env`) - the gateway's own keys,
  comma-separated. Callers use the gateway as a plain OpenAI API and send one
  as `Authorization: Bearer <key>`. Every route answers 401 without it except
  `/health` and `/gateway/metrics`. Empty = no key is asked.
- `EMBEDDINGS_API_KEY` (`deploy/embeddings/.env`) - the engine's key, given
  to the gateway as `GATEWAY_BACKEND_API_KEY`. The gateway sends it on every
  proxied request and drops the caller's `Authorization`, so the engine key
  never leaves the gateway and a gateway key never reaches the engine.

## Smoke Check

```bash
KEY=<one of GATEWAY_API_KEYS>

curl -fsS http://127.0.0.1:11000/v1/models -H "Authorization: Bearer $KEY"

curl -fsS http://127.0.0.1:11000/v1/embeddings \
  -H "Authorization: Bearer $KEY" \
  -H 'content-type: application/json' \
  -d '{"model":"embeddings-model","input":["hello","world"]}'

curl -fsS http://127.0.0.1:11000/gateway/metrics
```

Unit tests: `cd gateway && pip install -r requirements-dev.txt && pytest`.

## Dashboards

Grafana is not part of either compose stack. Import JSON from
`observability/dashboards/` into an existing Grafana:

- `backend-vllm-embeddings-prometheus.json`
- `gateway-prometheus-overview.json`
- `gateway-loki-events.json`

See `docs/` for details.
