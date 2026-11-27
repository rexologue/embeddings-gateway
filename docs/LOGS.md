# Logs

The gateway writes structured events to Loki:

- `embeddings_request`
- `embeddings_response`
- `embeddings_error`
- `embeddings_rejected` - a request refused without a valid gateway key
  (`warn_reason=unauthorized`, status 401). Its Loki `route` label is the
  fixed `rejected`; the path is in the event, the query string is not.

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

Request headers are logged with `authorization`, `x-api-key`, `api-key` and
cookies masked as `***`, so neither a gateway key nor the engine key reaches
Loki.

Input texts are not logged. This keeps document chunks and knowledge-base
content out of Loki.
