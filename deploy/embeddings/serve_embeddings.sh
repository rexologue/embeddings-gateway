#!/usr/bin/env bash
set -euo pipefail

MODEL_NAME="${MODEL_NAME:-/model}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-embeddings-model}"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
API_KEY="${API_KEY:-}"

RUNNER="${RUNNER:-pooling}"
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-1}"
PIPELINE_PARALLEL_SIZE="${PIPELINE_PARALLEL_SIZE:-1}"

MAX_MODEL_LEN="${MAX_MODEL_LEN:-24768}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.22}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-32}"
MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-32768}"

TOKENIZER_MODE="${TOKENIZER_MODE:-auto}"
DTYPE="${DTYPE:-auto}"
TRUST_REMOTE_CODE="${TRUST_REMOTE_CODE:-0}"
LOAD_FORMAT="${LOAD_FORMAT:-auto}"
POOLER_CONFIG="${POOLER_CONFIG:-}"
UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-warning}"

ARGS=(
  "$MODEL_NAME"
  "--host" "$HOST"
  "--port" "$PORT"
  "--served-model-name" "$SERVED_MODEL_NAME"
  "--runner" "$RUNNER"
  "--tensor-parallel-size" "$TENSOR_PARALLEL_SIZE"
  "--pipeline-parallel-size" "$PIPELINE_PARALLEL_SIZE"
  "--max-model-len" "$MAX_MODEL_LEN"
  "--gpu-memory-utilization" "$GPU_MEMORY_UTILIZATION"
  "--max-num-seqs" "$MAX_NUM_SEQS"
  "--max-num-batched-tokens" "$MAX_NUM_BATCHED_TOKENS"
  "--tokenizer-mode" "$TOKENIZER_MODE"
  "--dtype" "$DTYPE"
  "--load-format" "$LOAD_FORMAT"
  "--uvicorn-log-level" "$UVICORN_LOG_LEVEL"
  "--generation-config" "vllm"
  "--enable-request-id-headers"
)

if [[ -n "$API_KEY" ]]; then
  ARGS+=("--api-key" "$API_KEY")
fi

if [[ "$TRUST_REMOTE_CODE" == "1" ]]; then
  ARGS+=("--trust-remote-code")
fi

if [[ -n "$POOLER_CONFIG" ]]; then
  ARGS+=("--pooler-config" "$POOLER_CONFIG")
fi

echo "vLLM embeddings model: $MODEL_NAME"
echo "served model name:     $SERVED_MODEL_NAME"
echo "listen:                $HOST:$PORT"
echo "metrics:               /metrics"
echo "OpenAI endpoint:       /v1/embeddings"

exec vllm serve "${ARGS[@]}"
