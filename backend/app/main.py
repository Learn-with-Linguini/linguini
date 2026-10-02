"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai import build_tracer, load_ai_settings
from app.ai.features.object_grounding import ObjectGroundingError
from app.ai.registry import build_image_moderator, build_object_grounder
from app.api.learning_errors import register_learning_errors
from app.api.router import api_router
from app.config import get_allowed_origins
from app.database import create_database_engine
from app.services.auth import SupabaseTokenVerifier, load_auth_settings
from app.services.background import ThreadPoolBackgroundRunner

logger = logging.getLogger(__name__)
server_logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_database_engine()
    app.state.database_engine = engine
    app.state.background_runner = ThreadPoolBackgroundRunner()
    app.state.ai_tracer = build_tracer(app.state.ai_settings)
    auth_settings = app.state.auth_settings
    if auth_settings.mode == "demo":
        server_logger.warning(
            "Auth mode: demo — requests without a bearer token use DEMO_USER_ID. "
            "Do not use this mode in deployed environments."
        )
    else:
        app.state.token_verifier = SupabaseTokenVerifier(auth_settings)
        server_logger.info("Auth mode: %s", auth_settings.mode)
    grounding_config = app.state.ai_settings.object_grounding
    server_logger.info(
        "Object grounding configuration: provider=%s model=%s threshold=%s",
        grounding_config.provider.value, grounding_config.model_name,
        grounding_config.threshold,
    )
    try:
        app.state.object_grounder = build_object_grounder(app.state.ai_settings)
        if app.state.object_grounder is not None:
            server_logger.info("Grounding DINO object detector loaded.")
        else:
            server_logger.warning(
                "Grounding DINO is disabled; all markers use vision-model locations."
            )
    except ObjectGroundingError:
        app.state.object_grounder = None
        server_logger.warning(
            "Grounding DINO is unavailable; using vision-model marker locations.",
            exc_info=True,
        )
    moderation_config = app.state.ai_settings.image_moderation
    server_logger.info(
        "Image moderation configuration: provider=%s model=%s",
        moderation_config.provider.value, moderation_config.model_name,
    )
    try:
        app.state.image_moderator = build_image_moderator(app.state.ai_settings)
        if app.state.image_moderator is None:
            server_logger.warning(
                "Image moderation is disabled; uploads skip the moderation check."
            )
    except Exception:
        app.state.image_moderator = None
        server_logger.warning(
            "Image moderation is unavailable; uploads skip the moderation check.",
            exc_info=True,
        )
    try:
        yield
    finally:
        try:
            app.state.ai_tracer.flush()
            app.state.ai_tracer.shutdown()
        except Exception:
            logger.warning("AI tracer shutdown failed", exc_info=True)
        app.state.background_runner.shutdown(wait=True)
        engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=lifespan,
        title="Linguini API",
        version="0.1.0",
        description=(
            "API contracts for Linguini's image-based language-learning sessions "
            "and once-daily journal."
        ),
    )
    app.state.ai_settings = load_ai_settings()
    app.state.auth_settings = load_auth_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_allowed_origins(),
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )
    register_learning_errors(app)
    app.include_router(api_router)
    return app


app = create_app()
