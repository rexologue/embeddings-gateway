"""Caller authentication with the gateway's own API keys.

Callers speak the plain OpenAI API to the gateway and know only a gateway key,
sent the usual way as ``Authorization: Bearer <key>``. The engine has a key of
its own (``GATEWAY_BACKEND_API_KEY``) that only the gateway holds: the caller's
``Authorization`` is never passed on, so a gateway key never reaches the
engine and an engine key is never handed to a caller.

Every route needs a key except the probes that callers without one rely on:
``/health`` (the container healthcheck) and ``/gateway/metrics`` (scraped by
VictoriaMetrics). The check runs before routing, so an unauthenticated caller
gets 401 on every other path, known or not, and learns nothing about which
exist.
"""

from __future__ import annotations

import hmac
from typing import Awaitable, Callable, Mapping

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

# Exact paths answered without a key. ``/health/`` or ``/metrics?x`` style
# variants are not these paths and need a key like everything else.
# The same paths as HEALTH_ROUTE and METRICS_ROUTE of app.routes, which imports
# this module.
OPEN_ROUTES = frozenset({"/health", "/gateway/metrics"})

REJECT_UNAUTHORIZED = "unauthorized"


def parse_api_keys(raw: str | None) -> tuple[str, ...]:
    """Return the gateway keys from a comma-separated setting, trimmed and unique.

    Several keys let a key be rotated without downtime, or each client have its
    own. An empty setting means no keys: every route is open.
    """

    keys: list[str] = []
    for item in (raw or "").split(","):
        key = item.strip()
        if not key:
            continue
        if any(char.isspace() for char in key):
            raise ValueError("GATEWAY_API_KEYS entries must not contain whitespace")
        if key not in keys:
            keys.append(key)

    return tuple(keys)


def bearer_token(headers: Mapping[str, str]) -> str | None:
    """Return the token of an ``Authorization: Bearer`` header, if there is one."""

    value = headers.get("authorization")
    if not value:
        return None

    scheme, _, token = value.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        return None

    return token


def is_authorized(token: str | None, keys: tuple[str, ...]) -> bool:
    """Return whether ``token`` is one of ``keys``, comparing in constant time.

    Every key is compared, so the time taken does not tell which key, or how
    much of one, the token matched.
    """

    if token is None:
        return False

    presented = token.encode()
    matched = False
    for key in keys:
        matched |= hmac.compare_digest(presented, key.encode())

    return matched


class ApiKeyMiddleware:
    """Answer requests without a valid gateway key before they reach a route.

    A pure ASGI middleware rather than ``BaseHTTPMiddleware``: it never touches
    the response, so any streamed response passes through untouched.
    ``on_reject`` builds the refusal, which keeps logging and counting it in one
    place with the gateway's other rejections.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        keys: tuple[str, ...],
        on_reject: Callable[[Request], Awaitable[Response]],
    ) -> None:
        self.app = app
        self.keys = keys
        self.on_reject = on_reject

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not self.keys
            or scope["path"] in OPEN_ROUTES
            or is_authorized(bearer_token(Headers(scope=scope)), self.keys)
        ):
            await self.app(scope, receive, send)
            return

        response = await self.on_reject(Request(scope, receive))
        await response(scope, receive, send)
