"""Runtime state container for shared gateway services."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.backend import OpenAICompatibleBackend
from app.loki_logging import GatewayLokiLogger
from app.metrics import GatewayMetrics
from app.settings import Settings
from app.tools.loki import LokiEventPublisher


@dataclass(slots=True)
class AppState:
    settings: Settings
    http: httpx.AsyncClient
    backend: OpenAICompatibleBackend
    metrics: GatewayMetrics
    loki: GatewayLokiLogger


def create_app_state(settings: Settings) -> AppState:
    timeout = httpx.Timeout(
        connect=settings.connect_timeout,
        read=settings.read_timeout,
        write=settings.write_timeout,
        pool=settings.pool_timeout,
    )
    limits = httpx.Limits(
        max_connections=settings.http_max_connections,
        max_keepalive_connections=settings.http_max_keepalive_connections,
    )
    http_client = httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=False)
    metrics = GatewayMetrics()
    backend = OpenAICompatibleBackend(base_url=settings.backend_base_url, http=http_client)
    loki_publisher = LokiEventPublisher(
        enabled=settings.loki_enabled,
        push_url=settings.loki_push_url,
        batch_size=settings.loki_batch_size,
        flush_interval_sec=settings.loki_flush_interval_sec,
        queue_max_size=settings.loki_queue_max_size,
        loki_app_name=settings.loki_app_name,
        metrics=metrics,
    )
    loki = GatewayLokiLogger(loki_publisher)
    return AppState(
        settings=settings,
        http=http_client,
        backend=backend,
        metrics=metrics,
        loki=loki,
    )
