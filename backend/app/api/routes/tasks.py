from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import get_task_service
from app.api.errors import service_not_implemented
from app.schemas.tasks import (
    CheckVocabularyAnswerRequest,
    CheckVocabularyAnswerResponse,
    SessionTaskPublic,
    SkipTaskRequest,
    SubmitTaskAttemptRequest,
    TaskActionResponse,
    TaskHint,
)
from app.services.tasks import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


@router.get("/{task_id}", response_model=SessionTaskPublic)
def get_task(
    task_id: UUID, service: Annotated[TaskService, Depends(get_task_service)]
) -> SessionTaskPublic:
    return service.get(task_id)


@router.post("/{task_id}/start", response_model=TaskActionResponse)
def start_task(task_id: UUID, service: TaskServiceDep) -> TaskActionResponse:
    return service.action(task_id, "start")


@router.post("/{task_id}/attempts", response_model=TaskActionResponse)
def submit_task_attempt(
    task_id: UUID, request: SubmitTaskAttemptRequest, service: TaskServiceDep
) -> TaskActionResponse:
    return service.action(task_id, "attempt", request)


@router.post("/{task_id}/check-vocabulary-answer", response_model=CheckVocabularyAnswerResponse)
def check_vocabulary_answer(
    task_id: UUID, request: CheckVocabularyAnswerRequest, service: TaskServiceDep
) -> CheckVocabularyAnswerResponse:
    return service.check_vocabulary_answer(task_id, request.question_id, request.option_id)


@router.post("/{task_id}/hints", response_model=TaskHint)
async def request_task_hint(task_id: UUID) -> TaskHint:
    service_not_implemented("Request task hint")


@router.post("/{task_id}/complete", response_model=TaskActionResponse)
def complete_task(task_id: UUID, service: TaskServiceDep) -> TaskActionResponse:
    return service.action(task_id, "complete")


@router.post("/{task_id}/skip", response_model=TaskActionResponse)
def skip_task(
    task_id: UUID, request: SkipTaskRequest, service: TaskServiceDep
) -> TaskActionResponse:
    return service.action(task_id, "skip", request)
