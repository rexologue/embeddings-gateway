# Deployment

The deployment is intentionally split into backend and gateway stacks. This
keeps vLLM operational metrics independent from gateway/API metrics.

## Backend Stack

`deploy/embeddings` contains:

- vLLM OpenAI-compatible embeddings server;
- Prometheus scraping vLLM `/metrics`.

Create local settings:

```bash
cp deploy/embeddings/.env.example deploy/embeddings/.env
```

Edit `deploy/embeddings/.env`:

- `EMBEDDINGS_MODEL_PATH` points to the local model directory;
- `CUDA_VISIBLE_DEVICES` selects the GPU;
- `EMBEDDINGS_HTTP_PORT` exposes the direct backend debug API;
- `EMBEDDINGS_PROMETHEUS_HTTP_PORT` exposes backend Prometheus.

Start:

```bash
cd deploy/embeddings
docker compose --env-file .env -f docker-compose.yaml up -d
```

Useful URLs:

- vLLM API: `http://0.0.0.0:11010`
- vLLM metrics: `http://0.0.0.0:11010/metrics`
- backend Prometheus: `http://0.0.0.0:11101`

## Gateway Stack

`deploy/gateway` contains:

- FastAPI API gateway;
- Prometheus scraping gateway `/gateway/metrics`;
- Loki for structured gateway request/response/error events.

Create local settings:

```bash
cp deploy/gateway/.env.example deploy/gateway/.env
```

The default backend URL is:

```text
GATEWAY_BACKEND_BASE_URL=http://host.docker.gateway:11010
```

That matches the default backend debug port from `deploy/embeddings`.

Start:

```bash
cd deploy/gateway
docker compose --env-file .env -f docker-compose.yaml up -d --build
```

Useful URLs:

- gateway API: `http://0.0.0.0:11000`
- gateway health: `http://0.0.0.0:11000/health`
- gateway metrics: `http://0.0.0.0:11000/gateway/metrics`
- gateway Prometheus: `http://0.0.0.0:11100`
- Loki: `http://0.0.0.0:11102`

## Validation

Render compose configs:

```bash
cd deploy/embeddings
docker compose --env-file .env.example -f docker-compose.yaml config

cd ../gateway
docker compose --env-file .env.example -f docker-compose.yaml config
```

Smoke checks after startup:

```bash
curl -fsS http://127.0.0.1:11010/v1/models
curl -fsS http://127.0.0.1:11000/health
curl -fsS http://127.0.0.1:11000/v1/models
curl -fsS http://127.0.0.1:11000/gateway/metrics
curl -fsS http://127.0.0.1:11000/v1/embeddings \
  -H 'content-type: application/json' \
  -d '{"model":"embeddings-model","input":["hello","world"]}'
```
