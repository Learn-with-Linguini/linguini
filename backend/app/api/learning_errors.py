from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.ai.features.learning_tasks import LearningTaskGenerationError
from app.repositories.journals import JournalStorageError
from app.repositories.language_profiles import (
    LanguageProfileConflictError,
    LanguageProfileNotFoundError,
    LanguageProfileStorageError,
)
from app.repositories.learning import LearningStorageError
from app.repositories.media_assets import MediaAssetConflictError, MediaAssetStorageError
from app.repositories.practice import (
    ActiveSessionExistsError,
    ActiveSessionLimitReachedError,
    PracticeConflictError,
    PracticeNotFoundError,
    PracticeStorageError,
)
from app.repositories.scene_objects import (
    SceneObjectNotFoundError,
    SceneObjectReviewConflictError,
)
from app.repositories.scenes import SceneStorageError
from app.repositories.tasks import TaskConflictError, TaskNotFoundError, TaskStorageError
from app.repositories.users import UserRepositoryError
from app.services.image_storage import InvalidImageUpload, UploadObjectMissing
from app.services.journals import (
    FutureJournalDateError,
    JournalConflictError,
    JournalNotFoundError,
)
from app.services.language_profiles import NoActiveLanguageError
from app.services.learning import InvalidCursorError, ProgressNotFoundError
from app.services.media_assets import MediaAssetNotFoundError
from app.services.media_urls import MediaUrlError
from app.services.scene_analysis import SceneAnalysisError
from app.services.scenes import SceneNotFoundError
from app.services.users import UserNotFoundError


def register_learning_errors(app: FastAPI) -> None:
    errors = {
        InvalidImageUpload: (
            422,
            "invalid_image_upload",
            "Use a valid JPEG, PNG or WebP image up to 10 MB with the issued upload key.",
        ),
        UploadObjectMissing: (
            404,
            "upload_not_found",
            "Uploaded image not found. Upload the file before confirming.",
        ),
        MediaUrlError: (
            503,
            "media_url_error",
            "Unable to access media storage. Check backend Storage configuration and retry.",
        ),
        TaskNotFoundError: (404, "task_not_found", "Task or session not found."),
        TaskConflictError: (409, "task_conflict", "Task record conflicts with the current state."),
        TaskStorageError: (500, "task_storage_error", "Unable to load or save task records."),
        SceneObjectNotFoundError: (
            404,
            "scene_object_not_found",
            "Scene object or session not found.",
        ),
        SceneObjectReviewConflictError: (
            409,
            "scene_object_review_conflict",
            "This session has already ended.",
        ),
        MediaAssetStorageError: (
            500,
            "media_asset_storage_error",
            "Unable to load or save media metadata.",
        ),
        MediaAssetConflictError: (
            409,
            "media_asset_conflict",
            "Media asset or storage key already exists.",
        ),
        MediaAssetNotFoundError: (404, "media_asset_not_found", "Media asset not found."),
        PracticeStorageError: (
            500,
            "practice_storage_error",
            "Unable to load or save practice. Retry the action.",
        ),
        PracticeNotFoundError: (
            404,
            "practice_not_found",
            "Session or scene not found for the active language.",
        ),
        SceneAnalysisError: (
            502,
            "scene_analysis_failed",
            "Scene analysis failed. Start a new practice session.",
        ),
        LearningTaskGenerationError: (
            502,
            "learning_task_generation_failed",
            "We couldn't create your learning tasks. Please try again.",
        ),
        PracticeConflictError: (
            409,
            "practice_conflict",
            "This practice action is not valid for the current session.",
        ),
        ActiveSessionExistsError: (
            409,
            "active_session_exists",
            "You have a practice session in progress.",
        ),
        ActiveSessionLimitReachedError: (
            409,
            "active_session_limit_reached",
            "You can keep up to three unfinished practices open at once.",
        ),
        JournalStorageError: (500, "journal_storage_error", "Unable to load or save journal data."),
        JournalNotFoundError: (404, "journal_not_found", "Journal not found."),
        FutureJournalDateError: (
            409,
            "journal_future_date",
            "Cannot create a journal entry for a future date.",
        ),
        JournalConflictError: (
            409,
            "journal_conflict",
            "Journal action conflicts with its language, references or current revision.",
        ),
        LanguageProfileStorageError: (
            500,
            "language_profile_storage_error",
            "Unable to load or save language profiles.",
        ),
        LanguageProfileNotFoundError: (
            404,
            "language_profile_not_found",
            "Language profile not found.",
        ),
        LanguageProfileConflictError: (
            409,
            "language_profile_exists",
            "This language profile already exists.",
        ),
        NoActiveLanguageError: (
            409,
            "no_active_language",
            "Choose a target language in your profile.",
        ),
        SceneStorageError: (500, "scene_storage_error", "Unable to load scene data."),
        SceneNotFoundError: (404, "scene_not_found", "Scene not found."),
        LearningStorageError: (500, "learning_storage_error", "Unable to load learning data."),
        UserRepositoryError: (500, "user_storage_error", "Unable to load demo user data."),
        UserNotFoundError: (404, "user_not_found", "The configured demo user was not found."),
        ProgressNotFoundError: (404, "progress_not_found", "No progress found for this user."),
        InvalidCursorError: (400, "invalid_cursor", "Invalid vocabulary cursor."),
    }

    async def handle_error(request: Request, exc: Exception) -> JSONResponse:
        status, code, message = errors[type(exc)]
        if isinstance(exc, PracticeConflictError):
            message = str(exc)
        detail = {"code": code, "message": message}
        if isinstance(exc, ActiveSessionExistsError):
            detail["activeSessionId"] = str(exc.active_session_id)
        return JSONResponse(status_code=status, content={"detail": detail})

    for error_type in errors:
        app.add_exception_handler(error_type, handle_error)
