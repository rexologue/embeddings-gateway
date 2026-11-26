# Deployment

The deployment is intentionally split into backend and gateway stacks. This
keeps vLLM operational metrics independent from gateway/API metrics.

## Backend Stack

`deploy/embeddings` contains:

- vLLM OpenAI-compatible embeddings server (pooling runner);
- Prometheus scraping vLLM `/metrics`.

Settings are split in two files, both local and not in git:

- `.env` - from `.env.example`: image, weights, GPU, host port, API key;
- `serve_embeddings.sh` - from `serve_embeddings.example.sh`: everything vLLM
  is started with (pooling, memory, batching, served model name). Every
  parameter there is commented: what it does and when to change it.

```bash
cd deploy/embeddings
cp .env.example .env
cp serve_embeddings.example.sh serve_embeddings.sh
```

Edit `deploy/embeddings/.env`:

- `EMBEDDINGS_MODEL_PATH` points to the local model directory;
- `EMBEDDINGS_GPU_DEVICES` selects the GPU(s);
- `EMBEDDINGS_HTTP_PORT` exposes the backend API the gateway calls;
- `EMBEDDINGS_API_KEY` - optional engine key;
- `EMBEDDINGS_PROMETHEUS_HTTP_PORT` exposes backend Prometheus.

Edit `deploy/embeddings/serve_embeddings.sh`, at least:

- `SERVED_MODEL_NAME` - the `model` clients send;
- `GPU_MEMORY_UTILIZATION`, `MAX_MODEL_LEN`, `MAX_NUM_BATCHED_TOKENS` - by the
  GPU and what else runs on it. The share is of the whole card: on a GPU
  shared with an LLM the shares of all engines must add up to less than ~0.95.

A changed `serve_embeddings.sh` takes effect on container restart:
`docker compose restart embeddings-vllm`.

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

Smoke checks after startup (`docker compose ps` shows the engine `healthy`
once the weights are loaded):

```bash
curl -fsS http://127.0.0.1:11010/health
curl -fsS http://127.0.0.1:11010/v1/models
curl -fsS http://127.0.0.1:11000/health
curl -fsS http://127.0.0.1:11000/v1/models
curl -fsS http://127.0.0.1:11000/gateway/metrics
curl -fsS http://127.0.0.1:11000/v1/embeddings \
  -H 'content-type: application/json' \
  -d '{"model":"embeddings-model","input":["hello","world"]}'
```
