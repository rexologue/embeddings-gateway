"""Tests for the gateway's own API keys.

Callers know only a gateway key and send it as ``Authorization: Bearer``; the
engine key stays with the gateway. These tests pin which routes are open, what
a refused caller gets, that the refusal is logged without the key, and that a
gateway key is never passed on to the engine.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from app.auth import ApiKeyMiddleware, bearer_token, is_authorized, parse_api_keys
from app.backend import OpenAICompatibleBackend
from app.loki_logging import GatewayLokiLogger
from app.routes import reject_unauthorized

KEY = "gw-key-1"
OTHER_KEY = "gw-key-2"


class RecordingPublisher:
    """Stands in for the Loki publisher and keeps every submitted event."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def submit(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class RecordingMetrics:
    """Stands in for GatewayMetrics and keeps every rejection."""

    def __init__(self) -> None:
        self.rejected: list[tuple[str, str]] = []

    def rejected_request(self, *, method: str, reason: str) -> None:
        self.rejected.append((method, reason))


def make_app(keys: tuple[str, ...]) -> tuple[FastAPI, RecordingPublisher, RecordingMetrics]:
    """Return a small app with the gateway's paths, middleware and refusal path."""

    app = FastAPI()
    publisher = RecordingPublisher()
    metrics = RecordingMetrics()
    app.state.gateway_state = SimpleNamespace(loki=GatewayLokiLogger(publisher), metrics=metrics)

    for path in ("/health", "/gateway/metrics", "/v1/models", "/"):
        app.add_api_route(path, lambda: PlainTextResponse("ok"), methods=["GET"])
    for path in ("/v1/embeddings", "/tokenize"):
        app.add_api_route(path, lambda: PlainTextResponse("ok"), methods=["POST"])
    app.add_middleware(ApiKeyMiddleware, keys=keys, on_reject=reject_unauthorized)

    return app, publisher, metrics


def call(app: FastAPI, method: str, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://gw") as client:
            return await client.request(method, url, headers=headers)

    return asyncio.run(run())


def test_keys_are_trimmed_deduplicated_and_may_be_empty() -> None:
    assert parse_api_keys(f" {KEY} , {OTHER_KEY},{KEY}, ") == (KEY, OTHER_KEY)
    assert parse_api_keys("") == ()
    assert parse_api_keys(None) == ()


def test_a_key_with_whitespace_inside_is_refused() -> None:
    with pytest.raises(ValueError):
        parse_api_keys("two words")


@pytest.mark.parametrize(
    ("header", "token"),
    [
        (f"Bearer {KEY}", KEY),
        (f"bearer {KEY}", KEY),
        (f"Bearer   {KEY}  ", KEY),
        (f"Basic {KEY}", None),
        ("Bearer", None),
        ("Bearer ", None),
        (KEY, None),
    ],
)
def test_bearer_token_is_read_from_authorization(header: str, token: str | None) -> None:
    assert bearer_token({"authorization": header}) == token


def test_any_configured_key_is_accepted_and_nothing_else() -> None:
    keys = (KEY, OTHER_KEY)

    assert is_authorized(KEY, keys)
    assert is_authorized(OTHER_KEY, keys)
    assert not is_authorized("gw-key-3", keys)
    assert not is_authorized(KEY[:-1], keys)
    assert not is_authorized("", keys)
    assert not is_authorized(None, keys)


@pytest.mark.parametrize("path", ["/health", "/gateway/metrics"])
def test_probes_are_open_without_a_key(path: str) -> None:
    app, publisher, _ = make_app((KEY,))

    assert call(app, "GET", path).status_code == 200
    assert publisher.events == []


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/v1/embeddings"),
        ("POST", "/tokenize"),
        ("GET", "/v1/models"),
        ("GET", "/"),
        ("GET", "/metrics"),
        ("GET", "/no/such/route"),
        ("GET", "/health/"),
    ],
)
def test_everything_else_needs_a_key(method: str, path: str) -> None:
    app, _, _ = make_app((KEY,))

    assert call(app, method, path).status_code == 401
    assert call(app, method, path, {"Authorization": "Bearer wrong"}).status_code == 401


def test_a_valid_key_passes() -> None:
    app, publisher, metrics = make_app((KEY, OTHER_KEY))

    reply = call(app, "POST", "/v1/embeddings", {"Authorization": f"Bearer {OTHER_KEY}"})

    assert reply.status_code == 200
    assert publisher.events == []
    assert metrics.rejected == []


def test_refusal_is_openai_shaped_counted_and_logged_without_the_key() -> None:
    app, publisher, metrics = make_app((KEY,))

    reply = call(
        app,
        "GET",
        "/v1/models?api_key=leaked-in-url&limit=5",
        {"Authorization": "Bearer leaked-in-header", "User-Agent": "probe"},
    )

    assert reply.status_code == 401
    assert reply.headers["www-authenticate"] == "Bearer"
    error = reply.json()["error"]
    assert error["type"] == "invalid_request_error"
    assert error["code"] == "invalid_api_key"

    assert metrics.rejected == [("GET", "unauthorized")]
    [event] = publisher.events
    assert event["route"] == "rejected"
    assert event["path"] == "/v1/models"
    assert event["warn_reason"] == "unauthorized"
    assert event["status_code"] == 401
    assert event["request_headers"]["authorization"] == "***"
    assert event["request_headers"]["user-agent"] == "probe"
    assert "leaked" not in json.dumps(event)


def test_without_keys_every_route_is_open() -> None:
    app, _, _ = make_app(())

    assert call(app, "GET", "/v1/models").status_code == 200
    assert call(app, "POST", "/v1/embeddings").status_code == 200


def test_gateway_key_is_not_passed_to_an_engine_without_a_key() -> None:
    backend = OpenAICompatibleBackend(
        base_url="http://vllm:8000",
        http=httpx.AsyncClient(),
        api_key=None,
        drop_caller_authorization=True,
    )

    headers = backend.forwarded_headers(
        {"Authorization": f"Bearer {KEY}", "accept": "*/*"},
        request_id="r1",
    )

    assert not any(key.lower() == "authorization" for key in headers)
    assert headers["accept"] == "*/*"


def test_engine_key_replaces_the_gateway_key() -> None:
    backend = OpenAICompatibleBackend(
        base_url="http://vllm:8000",
        http=httpx.AsyncClient(),
        api_key="engine-key",
    )

    headers = backend.forwarded_headers({"authorization": f"Bearer {KEY}"}, request_id="r1")

    assert headers["authorization"] == "Bearer engine-key"


def test_without_any_key_the_caller_authorization_passes_through() -> None:
    backend = OpenAICompatibleBackend(base_url="http://vllm:8000", http=httpx.AsyncClient())

    headers = backend.forwarded_headers({"authorization": "Bearer caller"}, request_id="r1")

    assert headers["authorization"] == "Bearer caller"


def test_settings_keep_the_keys_out_of_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.settings import Settings

    monkeypatch.setenv("GATEWAY_API_KEYS", f"{KEY},{OTHER_KEY}")
    monkeypatch.setenv("GATEWAY_BACKEND_API_KEY", "engine-key")
    settings = Settings.from_env()

    assert settings.api_keys == (KEY, OTHER_KEY)
    assert KEY not in repr(settings)
    assert "engine-key" not in repr(settings)
