"""Runtime settings for the embeddings gateway."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    backend_base_url: str

    connect_timeout: float
    read_timeout: float
    write_timeout: float
    pool_timeout: float
    http_max_connections: int
    http_max_keepalive_connections: int

    loki_app_name: str
    loki_enabled: bool
    loki_push_url: str
    loki_batch_size: int
    loki_flush_interval_sec: float
    loki_queue_max_size: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            backend_base_url=os.getenv(
                "GATEWAY_BACKEND_BASE_URL",
                "http://embeddings-vllm:8000",
            ).rstrip("/"),
            connect_timeout=float(os.getenv("GATEWAY_TIMEOUT_CONNECT_SEC", "30")),
            read_timeout=float(os.getenv("GATEWAY_TIMEOUT_READ_SEC", "300")),
            write_timeout=float(os.getenv("GATEWAY_TIMEOUT_WRITE_SEC", "300")),
            pool_timeout=float(os.getenv("GATEWAY_TIMEOUT_POOL_SEC", "30")),
            http_max_connections=int(os.getenv("GATEWAY_HTTP_MAX_CONNECTIONS", "200")),
            http_max_keepalive_connections=int(
                os.getenv("GATEWAY_HTTP_MAX_KEEPALIVE_CONNECTIONS", "100")
            ),
            loki_app_name=os.getenv("GATEWAY_LOKI_APP_NAME", "embeddings-gateway"),
            loki_enabled=_get_bool_env("GATEWAY_LOKI_ENABLED", True),
            loki_push_url=os.getenv(
                "GATEWAY_LOKI_PUSH_URL",
                "http://embeddings-gateway-loki:3100/loki/api/v1/push",
            ),
            loki_batch_size=int(os.getenv("GATEWAY_LOKI_BATCH_SIZE", "200")),
            loki_flush_interval_sec=float(
                os.getenv("GATEWAY_LOKI_FLUSH_INTERVAL_SEC", "1.0")
            ),
            loki_queue_max_size=int(os.getenv("GATEWAY_LOKI_QUEUE_MAX_SIZE", "10000")),
        )
