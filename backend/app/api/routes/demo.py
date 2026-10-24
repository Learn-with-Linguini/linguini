"""Public, stateless guest-demo endpoint."""

import hashlib
import threading
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.dependencies import get_ai_runtime
from app.schemas.demo import DemoPhotoRequest, DemoPhotoResponse
from app.services.demo_lessons import DemoLessonError, DemoLessonService
from app.services.image_storage import InvalidImageUpload

router = APIRouter(prefix="/demo", tags=["demo"])
_WINDOW_SECONDS, _MAX_ATTEMPTS = 60 * 60, 5
_attempts: dict[str, deque[float]] = defaultdict(deque)
_attempt_lock = threading.Lock()


def _visitor_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    address = forwarded or (request.client.host if request.client else "unknown")
    agent = request.headers.get("user-agent", "")[:200]
    return hashlib.sha256(f"{address}|{agent}".encode()).hexdigest()


def _enforce_limit(request: Request) -> None:
    now, key = time.monotonic(), _visitor_key(request)
    with _attempt_lock:
        recent = _attempts[key]
        while recent and recent[0] <= now - _WINDOW_SECONDS:
            recent.popleft()
        if len(recent) >= _MAX_ATTEMPTS:
            raise HTTPException(status_code=429, detail={
                "code": "demo_rate_limited",
                "message": "You've tried several photo demos. Please try again later.",
            })
        recent.append(now)


def get_demo_lesson_service(request: Request) -> DemoLessonService:
    runtime = get_ai_runtime(request)
    return DemoLessonService(runtime.uploaded_scene_analyzer(), runtime.translator())


@router.post("/photo", response_model=DemoPhotoResponse)
def analyze_demo_photo(
    request: Request, body: DemoPhotoRequest,
    service: Annotated[DemoLessonService, Depends(get_demo_lesson_service)],
) -> DemoPhotoResponse:
    _enforce_limit(request)
    try:
        return service.analyze(body)
    except InvalidImageUpload as exc:
        raise HTTPException(status_code=400, detail={
            "code": "invalid_demo_image", "message": str(exc),
        }) from exc
    except DemoLessonError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "demo_unavailable", "message": str(exc),
        }) from exc
