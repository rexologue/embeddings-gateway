"""HTTP routes exposed by the embeddings gateway application."""

from __future__ import annotations

import asyncio
import time
from typing import cast

import httpx
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.http_utils import (
    parse_json_maybe,
    request_id_from_headers,
    response_headers,
)
from app.state import AppState
from app.utils import input_item_count, model_label

EMBEDDINGS_ROUTE = "/v1/embeddings"
MODELS_ROUTE = "/v1/models"
TOKENIZE_ROUTE = "/tokenize"
HEALTH_ROUTE = "/health"
METRICS_ROUTE = "/gateway/metrics"
ROOT_ROUTE = "/"


def _get_state(app: FastAPI) -> AppState:
    return cast(AppState, app.state.gateway_state)


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get(HEALTH_ROUTE)
    async def health(request: Request) -> Response:
        state = _get_state(request.app)
        try:
            backend_response = await state.backend.request(
                method="GET",
                route=MODELS_ROUTE,
                headers={},
                content=b"",
            )
        except httpx.HTTPError as exc:
            return JSONResponse(
                {"ok": False, "backend": "unavailable", "detail": type(exc).__name__},
                status_code=503,
            )

        return JSONResponse(
            {
                "ok": backend_response.status_code < 500,
                "backend_status_code": backend_response.status_code,
            },
            status_code=200 if backend_response.status_code < 500 else 503,
        )

    @router.get(METRICS_ROUTE)
    async def gateway_metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @router.api_route(EMBEDDINGS_ROUTE, methods=["POST"])
    async def embeddings(request: Request) -> Response:
        return await _proxy(request, route=EMBEDDINGS_ROUTE)

    @router.api_route(MODELS_ROUTE, methods=["GET"])
    async def models(request: Request) -> Response:
        return await _proxy(request, route=MODELS_ROUTE)

    @router.api_route(TOKENIZE_ROUTE, methods=["POST"])
    async def tokenize(request: Request) -> Response:
        return await _proxy(request, route=TOKENIZE_ROUTE)

    @router.api_route(
        "/v1/{full_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def generic_v1_proxy(full_path: str, request: Request) -> Response:
        return await _proxy(request, route=f"/v1/{full_path}")

    @router.get(ROOT_ROUTE)
    async def root() -> PlainTextResponse:
        return PlainTextResponse("Embeddings gateway is up")

    return router


async def _proxy(request: Request, *, route: str) -> Response:
    state = _get_state(request.app)
    method = request.method.upper()
    started_at = time.perf_counter()
    raw_body = await request.body()
    headers_in = {key: value for key, value in request.headers.items()}
    request_id = request_id_from_headers(headers_in)
    payload = parse_json_maybe(raw_body)
    model = model_label(payload)
    input_items = input_item_count(payload)

    metrics_context = state.metrics.context(route=route, method=method, model=model)
    metrics_context.request(body_bytes=len(raw_body), input_items=input_items)

    log_context = state.loki.context(
        route=route,
        method=method,
        request_id=request_id,
        model=model,
        input_items=input_items,
        headers_in=headers_in,
        raw_body=raw_body,
    )
    await log_context.request()

    backend_headers = state.backend.forwarded_headers(headers_in, request_id=request_id)

    try:
        backend_response = await state.backend.request(
            method=method,
            route=route,
            headers=backend_headers,
            content=raw_body,
            params=request.query_params,
        )
    except asyncio.CancelledError as exc:
        duration_sec = time.perf_counter() - started_at
        await log_context.error(exc, e2e_sec=duration_sec)
        metrics_context.response(
            status_code=None,
            cancelled=True,
            e2e_sec=duration_sec,
            response_body_bytes=0,
        )
        raise
    except Exception as exc:
        duration_sec = time.perf_counter() - started_at
        await log_context.error(exc, e2e_sec=duration_sec)
        metrics_context.response(
            status_code=None,
            cancelled=False,
            e2e_sec=duration_sec,
            response_body_bytes=0,
        )
        raise

    duration_sec = time.perf_counter() - started_at
    outbound_headers = response_headers(backend_response.headers, request_id=request_id)
    await log_context.response(
        status_code=backend_response.status_code,
        response_headers=outbound_headers,
        response_bytes=backend_response.content,
        e2e_sec=duration_sec,
    )
    metrics_context.response(
        status_code=backend_response.status_code,
        cancelled=False,
        e2e_sec=duration_sec,
        response_body_bytes=len(backend_response.content),
    )

    return Response(
        content=backend_response.content,
        status_code=backend_response.status_code,
        headers=outbound_headers,
        media_type=backend_response.headers.get("content-type"),
    )
