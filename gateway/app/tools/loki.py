"""Publish structured embeddings gateway events to Loki."""

from __future__ import annotations

import asyncio
import gzip
from collections import defaultdict
from typing import Any

import httpx
import orjson

from app.metrics import GatewayMetrics


class LokiEventPublisher:
    def __init__(
        self,
        *,
        enabled: bool,
        push_url: str,
        batch_size: int,
        flush_interval_sec: float,
        queue_max_size: int,
        loki_app_name: str,
        metrics: GatewayMetrics,
    ) -> None:
        self.metrics = metrics
        self.enabled = enabled
        self.push_url = push_url
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        self.queue_max_size = max(0, queue_max_size)
        self.loki_app_name = loki_app_name
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=self.queue_max_size
        )
        self._task: asyncio.Task[None] | None = None
        self._client: httpx.AsyncClient | None = None
        self._stopping = False

    async def start(self) -> None:
        if not self.enabled:
            return

        self._client = httpx.AsyncClient(timeout=30.0)
        self._task = asyncio.create_task(self._run(), name="loki-event-publisher")

    async def stop(self) -> None:
        if not self.enabled:
            return

        self._stopping = True

        if self._task is not None:
            await self.queue.put({"_flush": True})
            await self._task

        if self._client is not None:
            await self._client.aclose()

    async def submit(self, event: dict[str, Any]) -> None:
        if not self.enabled:
            return

        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.metrics.loki_event_dropped("queue_full")

    async def _run(self) -> None:
        batch: list[dict[str, Any]] = []
        while True:
            try:
                item = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=self.flush_interval_sec,
                )
                if item.get("_flush"):
                    if batch:
                        await self._publish_batch(batch)
                        batch = []

                    if self._stopping:
                        break

                    continue

                batch.append(item)

                if len(batch) >= self.batch_size:
                    await self._publish_batch(batch)
                    batch = []

            except asyncio.TimeoutError:
                if batch:
                    await self._publish_batch(batch)
                    batch = []

                if self._stopping and self.queue.empty():
                    break

    async def _publish_batch(self, events: list[dict[str, Any]]) -> None:
        if not events or self._client is None:
            return

        grouped: dict[tuple[tuple[str, str], ...], list[list[str]]] = defaultdict(list)
        for event in events:
            stream_labels = {
                "app": self.loki_app_name,
                "bucket": str(event.get("bucket", "unknown")),
                "route": str(event.get("route", "unknown")),
            }
            key = tuple(sorted(stream_labels.items()))
            grouped[key].append(
                [
                    str(int(event["ts_unix_ns"])),
                    orjson.dumps(event).decode("utf-8"),
                ]
            )

        body = {
            "streams": [
                {
                    "stream": dict(key),
                    "values": values,
                }
                for key, values in grouped.items()
            ]
        }
        encoded = gzip.compress(orjson.dumps(body))

        try:
            response = await self._client.post(
                self.push_url,
                content=encoded,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
            )
            response.raise_for_status()
            self.metrics.loki_push("success")
        except Exception:
            self.metrics.loki_push("error")
