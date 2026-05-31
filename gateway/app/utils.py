"""Embeddings request helpers."""

from __future__ import annotations

from typing import Any


def model_label(payload: Any | None) -> str:
    if not isinstance(payload, dict):
        return "unknown"

    model = payload.get("model")
    if not isinstance(model, str) or not model:
        return "unknown"

    return model[:128]


def input_item_count(payload: Any | None) -> int | None:
    if not isinstance(payload, dict) or "input" not in payload:
        return None

    value = payload["input"]
    if isinstance(value, str):
        return 1
    if isinstance(value, list):
        return len(value)
    return None
