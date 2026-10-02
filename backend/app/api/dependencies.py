"""FastAPI wiring for PostgreSQL persistence and the read-only scene catalog."""

import logging
import os
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from app.ai import (
    AiFeature,
    AiProvider,
    AiSettings,
    AITracer,
    NoOpAITracer,
    load_ai_settings,
)
from app.ai.features.object_grounding import ObjectGroundingError
from app.ai.features.scene_analysis import RoutedSceneAnalyzer
from app.ai.instrumentation import TracedISpyGuessGenerator
from app.ai.openrouter import OPENROUTER_BASE_URL
from app.ai.registry import (
    build_image_moderator,
    build_ispy_clue_generator,
    build_learning_task_generator,
    build_object_grounder,
    build_scene_translator,
    build_uploaded_scene_analyzer,
)
from app.api.auth import get_current_user_id
from app.config import get_media_public_base_url, get_private_media_urls
from app.repositories.journals import JournalRepository
from app.repositories.language_profiles import LanguageProfileRepository
from app.repositories.learning import LearningRepository
from app.repositories.media_assets import MediaAssetRepository
from app.repositories.postgres.journals import PostgresJournalRepository
from app.repositories.postgres.language_profiles import (
    PostgresLanguageProfileRepository,
)
from app.repositories.postgres.media_assets import PostgresMediaAssetRepository
from app.repositories.postgres.practice import (
    SessionBackedLearningRepository,
)
from app.repositories.postgres.scenes import PostgresSceneRepository
from app.repositories.postgres.tasks import PostgresTaskRepository
from app.repositories.postgres.users import PostgresUserRepository
from app.repositories.postgres.vocabulary import PostgresVocabularyRepository
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.repositories.scenes import SceneRepository
from app.repositories.users import UserRepository
from app.services.image_derivatives import ImageDerivatives
from app.services.image_storage import ImageStorage
from app.services.journals import JournalService
from app.services.language_profiles import LanguageProfileService
from app.services.learning import LearningService
from app.services.media_assets import MediaAssetService
from app.services.openai_ispy_guess import OpenAIISpyGuessGenerator
from app.services.practice import PracticeService
from app.services.scene_analysis import DeterministicSceneAnalyzer
from app.services.scenes import SceneService
from app.services.tasks import TaskService
from app.services.users import UserService


def get_user_repository(request: Request) -> UserRepository:
    return PostgresUserRepository(request.app.state.database_engine)


def get_journal_repository(
    request: Request, user_id: Annotated[UUID, Depends(get_current_user_id)]
) -> JournalRepository:
    return PostgresJournalRepository(request.app.state.database_engine, user_id)


def get_language_profile_repository(request: Request) -> LanguageProfileRepository:
    return PostgresLanguageProfileRepository(request.app.state.database_engine)


def get_user_service(
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> UserService:
    return UserService(repository, user_id)


def get_language_profile_service(
    repository: Annotated[LanguageProfileRepository, Depends(get_language_profile_repository)],
    users: Annotated[UserService, Depends(get_user_service)],
) -> LanguageProfileService:
    return LanguageProfileService(repository, users)


def get_active_language(
    service: Annotated[LanguageProfileService, Depends(get_language_profile_service)],
) -> str:
    return service.active_language()


def get_journal_service(
    request: Request,
    repository: Annotated[JournalRepository, Depends(get_journal_repository)],
    users: Annotated[UserService, Depends(get_user_service)],
    profiles: Annotated[LanguageProfileService, Depends(get_language_profile_service)],
) -> JournalService:
    return JournalService(
        repository,
        users,
        profiles,
        get_media_asset_repository(request),
        get_media_public_base_url(),
        get_private_media_urls(),
        PostgresVocabularyRepository(request.app.state.database_engine),
    )


def get_learning_repository(
    request: Request, user_id: Annotated[UUID, Depends(get_current_user_id)]
) -> LearningRepository:
    return SessionBackedLearningRepository(
        request.app.state.database_engine,
        user_id,
        PostgresVocabularyRepository(request.app.state.database_engine),
    )


def get_scene_repository(request: Request) -> SceneRepository:
    return PostgresSceneRepository(request.app.state.database_engine)


def get_media_asset_repository(request: Request) -> MediaAssetRepository:
    return PostgresMediaAssetRepository(request.app.state.database_engine)


# One shared derivative cache per process so its LRU survives across requests.
_IMAGE_DERIVATIVES: ImageDerivatives | None = None
_OBJECT_GROUNDER_UNINITIALIZED = object()
_OBJECT_GROUNDER = _OBJECT_GROUNDER_UNINITIALIZED
_IMAGE_MODERATOR_UNINITIALIZED = object()
_IMAGE_MODERATOR = _IMAGE_MODERATOR_UNINITIALIZED
logger = logging.getLogger(__name__)


def get_image_derivatives() -> ImageDerivatives:
    global _IMAGE_DERIVATIVES
    if _IMAGE_DERIVATIVES is None:
        _IMAGE_DERIVATIVES = ImageDerivatives(
            ImageStorage(
                os.getenv("SUPABASE_URL", "").strip(),
                os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
            )
        )
    return _IMAGE_DERIVATIVES


def get_object_grounder(request: Request, settings: AiSettings):
    """Load the optional local detector once; preserve analysis if it is unavailable."""
    if hasattr(request.app.state, "object_grounder"):
        return request.app.state.object_grounder
    global _OBJECT_GROUNDER
    if _OBJECT_GROUNDER is _OBJECT_GROUNDER_UNINITIALIZED:
        try:
            _OBJECT_GROUNDER = build_object_grounder(settings)
            if _OBJECT_GROUNDER is not None:
                logger.info("Grounding DINO object detector loaded.")
        except ObjectGroundingError:
            logger.warning("object grounding is unavailable; using model locations")
            _OBJECT_GROUNDER = None
    return _OBJECT_GROUNDER


def get_image_moderator(request: Request, settings: AiSettings):
    """Load the optional image moderator once; analysis fails open without it."""
    if hasattr(request.app.state, "image_moderator"):
        return request.app.state.image_moderator
    global _IMAGE_MODERATOR
    if _IMAGE_MODERATOR is _IMAGE_MODERATOR_UNINITIALIZED:
        try:
            _IMAGE_MODERATOR = build_image_moderator(settings)
            if _IMAGE_MODERATOR is not None:
                logger.info("Image moderation loaded.")
        except Exception:
            logger.warning("image moderation is unavailable; uploads skip the check")
            _IMAGE_MODERATOR = None
    return _IMAGE_MODERATOR


def get_media_asset_service(
    repository: Annotated[MediaAssetRepository, Depends(get_media_asset_repository)],
    users: Annotated[UserService, Depends(get_user_service)],
) -> MediaAssetService:
    return MediaAssetService(
        repository,
        users,
        ImageStorage(
            os.getenv("SUPABASE_URL", "").strip(),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        ),
        get_image_derivatives(),
    )


def get_scene_service(
    repository: Annotated[SceneRepository, Depends(get_scene_repository)],
) -> SceneService:
    return SceneService(repository, get_media_public_base_url(), get_private_media_urls())


def get_ai_settings(request: Request) -> AiSettings:
    """AI settings loaded at app startup; falls back to loading on demand."""
    settings = getattr(request.app.state, "ai_settings", None)
    if settings is None:
        settings = load_ai_settings()
    return settings


def get_ai_tracer(request: Request) -> AITracer:
    """Tracer built in the app lifespan; falls back to a no-op."""
    return getattr(request.app.state, "ai_tracer", None) or NoOpAITracer()


def get_ispy_guess_generator(settings: AiSettings, tracer: AITracer | None = None):
    """Build the target-blind I-Spy evaluator used by task generation and attempts."""
    config = settings.feature(AiFeature.ISPY_GUESS)
    if config.provider is AiProvider.NONE:
        return None
    if config.provider not in (AiProvider.OPENAI, AiProvider.OPENROUTER):
        raise ValueError(f"Unsupported ISPY_GUESS_PROVIDER: {config.provider}")
    if not settings.is_configured(config):
        return None
    return TracedISpyGuessGenerator(
        OpenAIISpyGuessGenerator(
            settings.api_key_for(config.provider),
            config.model_name,
            timeout_seconds=config.timeout_seconds,
            base_url=(
                OPENROUTER_BASE_URL
                if config.provider is AiProvider.OPENROUTER else None
            ),
        ),
        tracer or NoOpAITracer(),
        provider=config.provider.value,
        model=config.model_name,
        max_retries=config.max_retries,
    )


def get_practice_repository(
    request: Request, user_id: Annotated[UUID, Depends(get_current_user_id)]
) -> PostgresWorkflowRepository:
    engine = request.app.state.database_engine
    settings = get_ai_settings(request)
    deterministic = DeterministicSceneAnalyzer(engine)
    analyzer = deterministic
    storage = ImageStorage(
        os.getenv("SUPABASE_URL", "").strip(),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
    )

    tracer = get_ai_tracer(request)
    object_grounder = get_object_grounder(request, settings)
    image_moderator = get_image_moderator(request, settings)
    uploaded_analyzer = build_uploaded_scene_analyzer(
        settings,
        storage,
        tracer,
        object_grounder=object_grounder,
        image_moderator=image_moderator,
    )
    if uploaded_analyzer:
        analyzer = RoutedSceneAnalyzer(deterministic, uploaded_analyzer)

    translator = build_scene_translator(settings, tracer)

    learning_task_generator = build_learning_task_generator(settings, tracer)

    ispy_clue_generator = build_ispy_clue_generator(settings, tracer)
    return PostgresWorkflowRepository(
        engine,
        user_id,
        analyzer=analyzer,
        translator=translator,
        learning_task_generator=learning_task_generator,
        ispy_clue_generator=ispy_clue_generator,
        ispy_guess_generator=get_ispy_guess_generator(
            settings, get_ai_tracer(request)
        ),
        background=getattr(request.app.state, "background_runner", None),
    )


def get_practice_service(
    repository: Annotated[PostgresWorkflowRepository, Depends(get_practice_repository)],
    users: Annotated[UserService, Depends(get_user_service)],
    profiles: Annotated[LanguageProfileService, Depends(get_language_profile_service)],
) -> PracticeService:
    return PracticeService(repository, users, profiles)


def get_task_service(
    request: Request, users: Annotated[UserService, Depends(get_user_service)]
) -> TaskService:
    return TaskService(
        PostgresTaskRepository(request.app.state.database_engine),
        users,
        request.app.state.database_engine,
        ispy_guess_generator=get_ispy_guess_generator(
            get_ai_settings(request), get_ai_tracer(request)
        ),
    )


def get_learning_service(
    repository: Annotated[LearningRepository, Depends(get_learning_repository)],
    users: Annotated[UserService, Depends(get_user_service)],
) -> LearningService:
    return LearningService(repository, users)
