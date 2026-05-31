# Logs

The gateway writes structured events to Loki:

- `embeddings_request`
- `embeddings_response`
- `embeddings_error`

Each event includes operational metadata such as:

- `request_id`
- `route`
- `method`
- `model`
- `input_items`
- request or response body size
- response status code
- end-to-end duration
- error type and message for gateway errors

Input texts are not logged. This keeps document chunks and knowledge-base
content out of Loki.
