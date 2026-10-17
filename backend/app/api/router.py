"""Top-level API router assembly."""

from fastapi import APIRouter

from app.api.routes import (
    friends,
    game_resources,
    health,
    home,
    ispy,
    journals,
    media,
    onboarding,
    progress,
    rooms,
    sessions,
    support,
    tasks,
    users,
    vocabulary,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(users.router)
api_router.include_router(game_resources.router)
api_router.include_router(rooms.router)
api_router.include_router(friends.router)
api_router.include_router(home.router)
api_router.include_router(media.router)
api_router.include_router(onboarding.router)
api_router.include_router(sessions.router)
api_router.include_router(ispy.router)
api_router.include_router(support.router)
api_router.include_router(tasks.router)
api_router.include_router(vocabulary.router)
api_router.include_router(progress.router)
api_router.include_router(journals.router)
