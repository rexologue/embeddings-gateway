"""FastAPI application factory for the embeddings gateway."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.routes import create_router
from app.settings import Settings
from app.state import create_app_state


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
    return application


app = create_app()
