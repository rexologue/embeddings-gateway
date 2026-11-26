#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# serve_embeddings.sh
#
# Назначение:
#   Запуск одного OpenAI-compatible vLLM endpoint для эмбеддингов
#   (/v1/embeddings) на pooling runner'е с:
#   - явными параметрами памяти/батчинга под общую с другими движками GPU
#   - опциональной настройкой pooler'а (тип пулинга, нормализация)
#   - опциональными HF overrides (например, Matryoshka-размерности)
#   - опциональным API-ключом
#
# Скрипт не привязан к конкретной модели. Значения ниже подобраны для
# Qwen3-Embedding-0.6B на GPU, которую он делит с LLM. Pooler, overrides и
# trust_remote_code включай только после проверки документации конкретной
# модели и `vllm serve --help` своей версии vLLM: имена флагов pooling'а
# менялись между версиями.
#
# Как пользоваться:
#   cp serve_embeddings.example.sh serve_embeddings.sh
#   правь serve_embeddings.sh — его читает docker-compose.yaml, в git его нет.
###############################################################################

############################################
# REQUIRED
############################################
MODEL_NAME="/model"
# Путь к директории модели внутри контейнера.
# docker-compose.yaml монтирует сюда EMBEDDINGS_MODEL_PATH из .env.
# Меняй, только если монтируешь модель в другое место или берёшь её из HF Hub
# по имени (тогда нужен доступ в сеть и кэш HF).

############################################
# LISTEN / AUTH
############################################
HOST="0.0.0.0"
# Адрес, на котором слушает API внутри контейнера.
# 0.0.0.0 — нужно, чтобы порт можно было опубликовать наружу контейнера.
# Какой адрес хоста смотрит в сеть, решает EMBEDDINGS_HOST в .env.

PORT="8000"
# Порт API внутри контейнера. Наружу его публикует compose
# (EMBEDDINGS_HTTP_PORT), healthcheck тоже ходит сюда — меняй вместе с ними.

API_KEY="${EMBEDDINGS_API_KEY:-}"
# Если строка непустая, сервер требует Bearer token.
# Берётся из EMBEDDINGS_API_KEY в .env (compose передаёт его в контейнер),
# чтобы ключ не лежал в этом скрипте. Пусто — авторизация выключена.
# Шлюз (deploy/gateway) свой ключ не подставляет: он пробрасывает заголовок
# Authorization клиента, так что с ключом его должны слать клиенты.
# vLLM проверяет ключ только для /v1, /v2, /inference и /cohere: /tokenize,
# /health, /metrics и служебные маршруты остаются открытыми.

SERVED_MODEL_NAME="embeddings-model"
# Имя модели, которое клиент указывает в поле "model".
# Это внешний alias: клиенты и шлюз видят только его, путь к весам не светится.
# Пусто — vLLM отдаёт модель под MODEL_NAME.

############################################
# RUNNER / POOLING
############################################
RUNNER="pooling"
# Какой runner поднимает vLLM.
# pooling — модель отдаёт векторы (/v1/embeddings, /pooling, /score), а не текст.
# Для embedding-моделей это обязательно: иначе vLLM может принять её
# за генеративную (у Qwen3-Embedding архитектура Qwen3ForCausalLM).

CONVERT=""
# Во что превращать модель на pooling runner'е (--convert).
# Пусто — vLLM решает сам по конфигу модели (для Qwen3-Embedding — embed).
# embed — явно эмбеддинги; classify / reward — другие pooling-задачи.
# Задавай, если vLLM в логе выбрал не ту задачу.

POOLER_CONFIG=""
# JSON для --pooler-config: как сворачивать скрытые состояния в один вектор.
# Пусто — берётся из модели (для sentence-transformers — из 1_Pooling/ и
# modules.json; у Qwen3-Embedding это LAST + normalize).
# Пример: '{"pooling_type": "LAST", "normalize": true}'
# Меняй, только если модель описана иначе, чем её надо пулить: другой пулинг
# даёт другие векторы, и старый индекс с ними не совпадёт.

HF_OVERRIDES=""
# JSON для --hf-overrides: правки config.json модели без правки файлов.
# Пример для Matryoshka-моделей (поддержка поля "dimensions" в запросе):
# '{"is_matryoshka": true}'
# Пусто — конфиг модели как есть.

############################################
# PARALLELISM
############################################
TENSOR_PARALLEL_SIZE="1"
# На сколько GPU распиливается модель по тензорному параллелизму.
# Для embedding-моделей до нескольких B параметров — всегда 1: модель
# помещается на одну карту, а TP только добавит накладные расходы.

PIPELINE_PARALLEL_SIZE="1"
# Pipeline parallel — деление по слоям между GPU.
# Для эмбеддингов почти никогда не нужен: оставляй 1.

############################################
# MEMORY / BATCHING
############################################
MAX_MODEL_LEN="24768"
# Максимальная длина входа в токенах. Длиннее — запрос отклоняется (400).
# Не больше, чем поддерживает модель (max_position_embeddings в config.json;
# у Qwen3-Embedding-0.6B — 32768). Меньше — меньше памяти под KV cache на
# запрос и больше параллельных запросов.

GPU_MEMORY_UTILIZATION="0.1"
# Доля VRAM всей карты, которую vLLM занимает: веса + активации + KV cache.
# Это доля от ПОЛНОЙ памяти GPU, а не от свободной: на общей с LLM карте сумма
# долей всех движков должна оставаться меньше ~0.95.
# Ориентир: 0.6B в bf16 — ~1.2 ГБ весов; 0.1 от 96 ГБ даёт ~7.7 ГБ под KV
# cache, это ~72k токенов (около трёх запросов по 24k одновременно).
# Если в логе "Available KV cache memory" меньше, чем нужно на один
# MAX_MODEL_LEN, сервер не стартует — подними долю или уменьши MAX_MODEL_LEN.

MAX_NUM_SEQS="32"
# Сколько запросов (входов) обрабатывается одновременно.
# Каждый элемент списка input в одном запросе — отдельная последовательность.
# Больше — выше throughput на коротких текстах, но больше пиковая память.

MAX_NUM_BATCHED_TOKENS="8192"
# Сколько токенов vLLM обрабатывает за один шаг.
# Длинные входы режутся на куски этого размера (chunked prefill), так что он
# может быть меньше MAX_MODEL_LEN. Больше — выше throughput на пачках, но
# выше пик активаций и задержка соседних запросов.
# 8192 — для общей карты; на выделенной можно 16384–32768.

ENABLE_PREFIX_CACHING=""
# Кэш общих префиксов между запросами.
# Пусто — поведение vLLM по умолчанию для этой модели и пулинга.
# 0 — выключить (--no-enable-prefix-caching), 1 — включить.
# Для эмбеддингов выигрыш обычно мал: тексты редко начинаются одинаково.
# Исключение — общий длинный префикс-инструкция у всех запросов.

############################################
# TOKENIZER / DTYPE / LOADING
############################################
TOKENIZER_MODE="auto"
# auto — fast tokenizer, если есть. slow — медленный, для отладки
# расхождений токенизации. Обычно не трогать.

DTYPE="auto"
# Тип весов и вычислений. auto — из config.json модели (bf16 у Qwen3).
# float16 — для карт без bf16. float32 — только для отладки точности.

QUANTIZATION=""
# Квантование весов (fp8, awq, gptq, ...). Пусто — как в модели.
# Для маленьких embedding-моделей обычно не нужно: память уходит на KV cache,
# а не на веса, а качество векторов может просесть.

LOAD_FORMAT="auto"
# Формат загрузки весов. auto — safetensors, если есть.
# dummy — случайные веса для проверки памяти и скорости без загрузки модели.

TRUST_REMOTE_CODE="0"
# 1 — разрешить исполнять Python-код из репозитория модели.
# Нужно только моделям с собственной архитектурой (custom modeling_*.py).
# Без надобности не включай: это исполнение чужого кода.

############################################
# OBSERVABILITY / LOGGING
############################################
UVICORN_LOG_LEVEL="warning"
# Уровень логирования HTTP-сервера.
# error — минимум шума
# warning — обычно оптимально
# info — каждый запрос в логе
# debug — для глубокой отладки, очень шумно

ENABLE_REQUEST_ID_HEADERS="1"
# 1 — vLLM возвращает X-Request-Id: шлюз и логи движка связываются по нему.

DISABLE_ACCESS_LOG_FOR_ENDPOINTS="/health,/metrics,/ping"
# Эндпоинты, которые не пишутся в access log: их часто дёргают healthcheck
# и сбор метрик. Пусто — логировать всё.

############################################
# EXTRA / EXPERIMENTAL
############################################
EXTRA_ARGS=()
# Сюда складываются дополнительные флаги, которые не хочется выносить
# в отдельные переменные. Удобно для экспериментов и редких опций.

EXTRA_ARGS+=("--generation-config" "vllm")
# Не читать generation_config.json модели. Для эмбеддингов он не нужен,
# флаг лишь убирает лишнюю загрузку и предупреждения.

############################################
# Build argv
############################################
ARGS=()

# Core
ARGS+=("$MODEL_NAME")
ARGS+=("--host" "$HOST")
ARGS+=("--port" "$PORT")

# Auth
if [[ -n "$API_KEY" ]]; then
  ARGS+=("--api-key" "$API_KEY")
fi

if [[ -n "$SERVED_MODEL_NAME" ]]; then
  ARGS+=("--served-model-name" "$SERVED_MODEL_NAME")
fi

# Runner / pooling
ARGS+=("--runner" "$RUNNER")

if [[ -n "$CONVERT" ]]; then
  ARGS+=("--convert" "$CONVERT")
fi

if [[ -n "$POOLER_CONFIG" ]]; then
  ARGS+=("--pooler-config" "$POOLER_CONFIG")
fi

if [[ -n "$HF_OVERRIDES" ]]; then
  ARGS+=("--hf-overrides" "$HF_OVERRIDES")
fi

# Parallelism
ARGS+=("--tensor-parallel-size" "$TENSOR_PARALLEL_SIZE")
ARGS+=("--pipeline-parallel-size" "$PIPELINE_PARALLEL_SIZE")

# Model / memory
ARGS+=("--max-model-len" "$MAX_MODEL_LEN")
ARGS+=("--gpu-memory-utilization" "$GPU_MEMORY_UTILIZATION")
ARGS+=("--max-num-seqs" "$MAX_NUM_SEQS")
ARGS+=("--max-num-batched-tokens" "$MAX_NUM_BATCHED_TOKENS")

case "$ENABLE_PREFIX_CACHING" in
  1) ARGS+=("--enable-prefix-caching") ;;
  0) ARGS+=("--no-enable-prefix-caching") ;;
  "") ;;
  *) echo "ENABLE_PREFIX_CACHING must be empty, 0 or 1, got: $ENABLE_PREFIX_CACHING" >&2; exit 1 ;;
esac

# Tokenizer / dtype / loading
ARGS+=("--tokenizer-mode" "$TOKENIZER_MODE")
ARGS+=("--dtype" "$DTYPE")
ARGS+=("--load-format" "$LOAD_FORMAT")

if [[ -n "$QUANTIZATION" ]]; then
  ARGS+=("--quantization" "$QUANTIZATION")
fi

if [[ "$TRUST_REMOTE_CODE" == "1" ]]; then
  ARGS+=("--trust-remote-code")
fi

# Logging
ARGS+=("--uvicorn-log-level" "$UVICORN_LOG_LEVEL")

if [[ "$ENABLE_REQUEST_ID_HEADERS" == "1" ]]; then
  ARGS+=("--enable-request-id-headers")
fi

if [[ -n "$DISABLE_ACCESS_LOG_FOR_ENDPOINTS" ]]; then
  ARGS+=("--disable-access-log-for-endpoints" "$DISABLE_ACCESS_LOG_FOR_ENDPOINTS")
fi

# Extra
if [[ "${#EXTRA_ARGS[@]}" -gt 0 ]]; then
  ARGS+=("${EXTRA_ARGS[@]}")
fi

############################################
# Pretty print config
############################################
echo "vLLM embeddings model:   $MODEL_NAME"
echo "listen:                  $HOST:$PORT"
echo "api key:                 $([[ -n "$API_KEY" ]] && echo enabled || echo disabled)"
echo "served model name:       $([[ -n "$SERVED_MODEL_NAME" ]] && echo "$SERVED_MODEL_NAME" || echo "$MODEL_NAME")"
echo "endpoints:               /v1/embeddings, /v1/models, /tokenize, /metrics"
echo
echo "runner:                  $RUNNER"
echo "convert:                 $([[ -n "$CONVERT" ]] && echo "$CONVERT" || echo auto)"
echo "pooler config:           $([[ -n "$POOLER_CONFIG" ]] && echo "$POOLER_CONFIG" || echo model)"
echo "hf overrides:            $([[ -n "$HF_OVERRIDES" ]] && echo "$HF_OVERRIDES" || echo none)"
echo
echo "tensor parallel:         $TENSOR_PARALLEL_SIZE"
echo "pipeline parallel:       $PIPELINE_PARALLEL_SIZE"
echo
echo "max model len:           $MAX_MODEL_LEN"
echo "gpu mem utilization:     $GPU_MEMORY_UTILIZATION"
echo "max num seqs:            $MAX_NUM_SEQS"
echo "max batched tokens:      $MAX_NUM_BATCHED_TOKENS"
echo "prefix caching:          $(case "$ENABLE_PREFIX_CACHING" in 1) echo enabled ;; 0) echo disabled ;; *) echo default ;; esac)"
echo
echo "tokenizer mode:          $TOKENIZER_MODE"
echo "dtype:                   $DTYPE"
echo "quantization:            $([[ -n "$QUANTIZATION" ]] && echo "$QUANTIZATION" || echo auto/model)"
echo "load format:             $LOAD_FORMAT"
echo "trust remote code:       $([[ "$TRUST_REMOTE_CODE" == "1" ]] && echo enabled || echo disabled)"
echo
echo "uvicorn log level:       $UVICORN_LOG_LEVEL"
echo "request id headers:      $([[ "$ENABLE_REQUEST_ID_HEADERS" == "1" ]] && echo enabled || echo disabled)"
echo
echo "full command:"
# The key is passed on the command line; keep it out of the log.
_printable=("${ARGS[@]}")
for i in "${!_printable[@]}"; do
  if [[ "${_printable[$i]}" == "--api-key" ]]; then
    _printable[$((i + 1))]="***"
  fi
done
printf ' %q' vllm serve "${_printable[@]}"
echo
echo

exec vllm serve "${ARGS[@]}"
