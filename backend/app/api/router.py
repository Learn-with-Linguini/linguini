"""Top-level API router assembly."""

from fastapi import APIRouter

from app.api.routes import (
    health,
    home,
    journals,
    media,
    progress,
    sessions,
    tasks,
    users,
    vocabulary,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(users.router)
api_router.include_router(home.router)
api_router.include_router(media.router)
api_router.include_router(sessions.router)
api_router.include_router(tasks.router)
api_router.include_router(vocabulary.router)
api_router.include_router(progress.router)
api_router.include_router(journals.router)
