"""Structured Loki events for embeddings gateway requests."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping

from app.http_utils import sanitize_headers, utc_now_iso
from app.tools.loki import LokiEventPublisher


@dataclass(slots=True)
class LokiRequestContext:
    logger: GatewayLokiLogger
    route: str
    method: str
    request_id: str
    model: str
    input_items: int | None
    headers_in: Mapping[str, str]
    raw_body: bytes

    async def request(self) -> None:
        await self.logger.log_request(self)

    async def response(
        self,
        *,
        status_code: int,
        response_headers: Mapping[str, str],
        response_bytes: bytes,
        e2e_sec: float,
    ) -> None:
        await self.logger.log_response(
            self,
            status_code=status_code,
            response_headers=response_headers,
            response_bytes=response_bytes,
            e2e_sec=e2e_sec,
        )

    async def error(self, error: BaseException, *, e2e_sec: float) -> None:
        await self.logger.log_error(self, error, e2e_sec=e2e_sec)


class GatewayLokiLogger:
    def __init__(self, publisher: LokiEventPublisher) -> None:
        self.publisher = publisher

    async def start(self) -> None:
        await self.publisher.start()

    async def stop(self) -> None:
        await self.publisher.stop()

    def context(
        self,
        *,
        route: str,
        method: str,
        request_id: str,
        model: str,
        input_items: int | None,
        headers_in: Mapping[str, str],
        raw_body: bytes,
    ) -> LokiRequestContext:
        return LokiRequestContext(
            logger=self,
            route=route,
            method=method,
            request_id=request_id,
            model=model,
            input_items=input_items,
            headers_in=headers_in,
            raw_body=raw_body,
        )

    async def log_request(self, context: LokiRequestContext) -> None:
        event = self._base_event(
            bucket="embeddings_request",
            level="info",
            event_type="request",
            context=context,
        )
        event.update(
            self._compact(
                {
                    "request_headers": sanitize_headers(context.headers_in),
                    "request_body_bytes": len(context.raw_body),
                }
            )
        )
        await self._submit(event)

    async def log_response(
        self,
        context: LokiRequestContext,
        *,
        status_code: int,
        response_headers: Mapping[str, str],
        response_bytes: bytes,
        e2e_sec: float,
    ) -> None:
        event = self._base_event(
            bucket="embeddings_response",
            level="warn" if status_code >= 400 else "info",
            event_type="response",
            context=context,
        )
        event.update(
            {
                "status_code": status_code,
                "e2e_sec": round(e2e_sec, 6),
                "response_body_bytes": len(response_bytes),
                "response_content_type": response_headers.get("content-type"),
            }
        )
        await self._submit(event)

    async def log_error(
        self,
        context: LokiRequestContext,
        error: BaseException,
        *,
        e2e_sec: float,
    ) -> None:
        event = self._base_event(
            bucket="embeddings_error",
            level="error",
            event_type="error",
            context=context,
        )
        event.update(
            {
                "e2e_sec": round(e2e_sec, 6),
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
        )
        await self._submit(event)

    async def _submit(self, event: dict[str, Any]) -> None:
        record = {
            "ts": utc_now_iso(),
            "ts_unix_ns": time.time_ns(),
            **event,
        }
        await self.publisher.submit(record)

    def _base_event(
        self,
        *,
        bucket: str,
        level: str,
        event_type: str,
        context: LokiRequestContext,
    ) -> dict[str, Any]:
        return self._compact(
            {
                "level": level,
                "bucket": bucket,
                "event_type": event_type,
                "route": context.route,
                "method": context.method,
                "request_id": context.request_id,
                "model": context.model,
                "input_items": context.input_items,
            }
        )

    @staticmethod
    def _compact(value: dict[str, Any]) -> dict[str, Any]:
        return {key: item for key, item in value.items() if item is not None}
