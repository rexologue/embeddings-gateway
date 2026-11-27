"""FastAPI application factory for the embeddings gateway."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.auth import ApiKeyMiddleware
from app.routes import create_router, reject_unauthorized
from app.settings import Settings
from app.state import create_app_state

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = create_app_state(settings)
        app.state.gateway_state = state
        await state.loki.start()

        try:
            yield
        finally:
            await state.loki.stop()
            await state.http.aclose()

    application = FastAPI(title="OpenAI-compatible Embeddings Gateway", lifespan=lifespan)
    application.include_router(create_router())
    application.add_middleware(
        ApiKeyMiddleware,
        keys=settings.api_keys,
        on_reject=reject_unauthorized,
    )
    if not settings.api_keys:
        logger.warning("GATEWAY_API_KEYS is empty: every route is open to anyone")
    return application


app = create_app()
