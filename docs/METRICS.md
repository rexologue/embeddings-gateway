# Metrics

There are two Prometheus instances by design.

## Backend vLLM Metrics

The backend Prometheus in `deploy/embeddings` scrapes vLLM directly:

```text
GET /metrics on embeddings-vllm:8000
```

This stack does not include DCGM exporter or node exporter. It tracks only
metrics exported by the vLLM OpenAI-compatible server.

The backend dashboard focuses on embeddings-relevant vLLM metrics:

- running and waiting requests;
- HTTP request rate;
- completed request rate;
- end-to-end request latency;
- queue and prefill latency;
- input token throughput;
- average input tokens per request;
- cache pressure;
- vLLM process memory and file descriptors;
- Prometheus scrape health.

Generation-specific panels such as TTFT, decode latency, output token
throughput, and inter-token latency are intentionally omitted because
`/v1/embeddings` is not a generation workload.

## Gateway Metrics

The gateway exposes:

```text
GET /gateway/metrics
```

Metrics:

- `embeddings_gateway_requests_total`
- `embeddings_gateway_responses_total`
- `embeddings_gateway_request_e2e_seconds`
- `embeddings_gateway_request_body_bytes`
- `embeddings_gateway_response_body_bytes`
- `embeddings_gateway_input_items`
- `embeddings_gateway_loki_push_total`
- `embeddings_gateway_loki_events_dropped_total`

Labels are intentionally low-cardinality: `route`, `method`, `model`,
`status_family`, and `result` where applicable. The gateway does not use
`request_id` or request text as Prometheus labels.
