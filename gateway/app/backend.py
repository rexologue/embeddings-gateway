"""HTTP client boundary for the OpenAI-compatible embeddings backend."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from app.http_utils import strip_hop_by_hop_headers


class OpenAICompatibleBackend:
    def __init__(
        self,
        *,
        base_url: str,
        http: httpx.AsyncClient,
        api_key: str | None = None,
    ) -> None:
        """``api_key`` is the engine's own key. When it is set, the gateway is the
        only one who knows it: every proxied request carries it, and the
        ``Authorization`` the caller sent is dropped, never passed on.
        """

        self.base_url = base_url.rstrip("/")
        self.http = http
        self.api_key = api_key or None

    def url_for(self, route: str) -> str:
        path = route if route.startswith("/") else f"/{route}"
        return f"{self.base_url}{path}"

    def forwarded_headers(
        self,
        headers: Mapping[str, str],
        *,
        request_id: str,
    ) -> dict[str, str]:
        """Return caller headers that are safe and useful to forward."""

        forwarded = strip_hop_by_hop_headers(headers)

        if self.api_key is not None:
            forwarded = {
                key: value
                for key, value in forwarded.items()
                if key.lower() != "authorization"
            }
            forwarded["authorization"] = f"Bearer {self.api_key}"

        forwarded["x-request-id"] = request_id
        return forwarded

    async def request(
        self,
        *,
        method: str,
        route: str,
        headers: Mapping[str, str],
        content: bytes,
        params: Any = None,
    ) -> httpx.Response:
        return await self.http.request(
            method=method,
            url=self.url_for(route),
            headers=headers,
            content=content,
            params=params,
        )
