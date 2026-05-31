"""Prometheus metrics for the embeddings gateway."""

from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import Counter, Histogram

REQUEST_COUNTER = Counter(
    "embeddings_gateway_requests_total",
    "Total number of requests accepted by the embeddings gateway",
    ["route", "method"],
)

RESPONSE_COUNTER = Counter(
    "embeddings_gateway_responses_total",
    "Total number of embeddings gateway responses by status family and result",
    ["route", "method", "status_family", "result"],
)

REQUEST_E2E_LATENCY = Histogram(
    "embeddings_gateway_request_e2e_seconds",
    "End-to-end request latency through the embeddings gateway",
    ["route", "method", "model", "status_family", "result"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)

REQUEST_BODY_BYTES = Histogram(
    "embeddings_gateway_request_body_bytes",
    "Request body size observed by the embeddings gateway",
    ["route", "method", "model"],
    buckets=(128, 512, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304),
)

RESPONSE_BODY_BYTES = Histogram(
    "embeddings_gateway_response_body_bytes",
    "Response body size observed by the embeddings gateway",
    ["route", "method", "model", "status_family", "result"],
    buckets=(128, 512, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304),
)

INPUT_ITEMS = Histogram(
    "embeddings_gateway_input_items",
    "Number of input items in embeddings requests",
    ["route", "method", "model"],
    buckets=(1, 2, 4, 8, 16, 32, 64, 128, 256, 512),
)

LOKI_PUSH_COUNTER = Counter(
    "embeddings_gateway_loki_push_total",
    "Log push attempts to Loki",
    ["status"],
)

LOKI_EVENTS_DROPPED_COUNTER = Counter(
    "embeddings_gateway_loki_events_dropped_total",
    "Loki events dropped before delivery",
    ["reason"],
)


@dataclass(frozen=True, slots=True)
class MetricsRequestContext:
    metrics: GatewayMetrics
    route: str
    method: str
    model: str

    def request(self, *, body_bytes: int, input_items: int | None) -> None:
        self.metrics.record_request(self, body_bytes=body_bytes, input_items=input_items)

    def response(
        self,
        *,
        status_code: int | None,
        cancelled: bool,
        e2e_sec: float,
        response_body_bytes: int,
    ) -> None:
        self.metrics.record_response(
            self,
            status_code=status_code,
            cancelled=cancelled,
            e2e_sec=e2e_sec,
            response_body_bytes=response_body_bytes,
        )


class GatewayMetrics:
    def context(self, *, route: str, method: str, model: str) -> MetricsRequestContext:
        return MetricsRequestContext(
            metrics=self,
            route=route,
            method=method,
            model=model or "unknown",
        )

    def record_request(
        self,
        context: MetricsRequestContext,
        *,
        body_bytes: int,
        input_items: int | None,
    ) -> None:
        REQUEST_COUNTER.labels(route=context.route, method=context.method).inc()
        REQUEST_BODY_BYTES.labels(
            route=context.route,
            method=context.method,
            model=context.model,
        ).observe(body_bytes)

        if input_items is not None:
            INPUT_ITEMS.labels(
                route=context.route,
                method=context.method,
                model=context.model,
            ).observe(input_items)

    def record_response(
        self,
        context: MetricsRequestContext,
        *,
        status_code: int | None,
        cancelled: bool,
        e2e_sec: float,
        response_body_bytes: int,
    ) -> None:
        labels = self.outcome_labels(
            route=context.route,
            method=context.method,
            model=context.model,
            status_code=status_code,
            cancelled=cancelled,
        )
        RESPONSE_COUNTER.labels(
            route=context.route,
            method=context.method,
            status_family=labels["status_family"],
            result=labels["result"],
        ).inc()
        REQUEST_E2E_LATENCY.labels(**labels).observe(e2e_sec)
        RESPONSE_BODY_BYTES.labels(**labels).observe(response_body_bytes)

    def loki_push(self, status: str) -> None:
        LOKI_PUSH_COUNTER.labels(status=status).inc()

    def loki_event_dropped(self, reason: str) -> None:
        LOKI_EVENTS_DROPPED_COUNTER.labels(reason=reason).inc()

    @staticmethod
    def outcome_labels(
        *,
        route: str,
        method: str,
        model: str,
        status_code: int | None,
        cancelled: bool,
    ) -> dict[str, str]:
        return {
            "route": route,
            "method": method,
            "model": model,
            "status_family": GatewayMetrics.status_family(status_code),
            "result": GatewayMetrics.result_from_status(status_code, cancelled),
        }

    @staticmethod
    def status_family(status_code: int | None) -> str:
        if status_code is None:
            return "unknown"
        return f"{status_code // 100}xx"

    @staticmethod
    def result_from_status(status_code: int | None, cancelled: bool) -> str:
        if cancelled:
            return "cancelled"
        if status_code is None or status_code >= 400:
            return "error"
        return "success"
