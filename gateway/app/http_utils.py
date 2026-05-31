"""Small HTTP helpers shared by gateway routes and logging."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from typing import Any

import orjson

SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
}

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def request_id_from_headers(headers: Mapping[str, str]) -> str:
    return headers.get("x-request-id") or headers.get("x-correlation-id") or uuid.uuid4().hex


def parse_json_maybe(raw_body: bytes) -> Any | None:
    if not raw_body:
        return None

    try:
        return orjson.loads(raw_body)
    except orjson.JSONDecodeError:
        return None


def sanitize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        sanitized[lowered] = "***" if lowered in SENSITIVE_KEYS else value
    return sanitized


def strip_hop_by_hop_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }


def response_headers(headers: Mapping[str, str], *, request_id: str) -> dict[str, str]:
    forwarded = strip_hop_by_hop_headers(headers)
    forwarded["x-request-id"] = request_id
    return forwarded
