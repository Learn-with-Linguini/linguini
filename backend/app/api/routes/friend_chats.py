"""Authenticated, private asynchronous I-Spy conversations."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.dependencies import get_friend_chat_service
from app.repositories.postgres.room_errors import RoomError
from app.schemas.friend_chats import (
    ChatAccess,
    ChatCommand,
    ChatCreate,
    ChatHelp,
    ChatJoin,
    ChatSnapshot,
    ChatSuggestion,
    GuessChatTarget,
    InvitePreview,
    InviteToken,
    ReportChat,
    SelectChatTarget,
    SendChatClue,
    StartChatRound,
)
from app.services.friend_chats import FriendChatService

router = APIRouter(prefix="/friend-chats", tags=["friend-chats"])
Service = Annotated[FriendChatService, Depends(get_friend_chat_service)]


def _call(fn, *args):
    try:
        return fn(*args)
    except RoomError as error:
        raise HTTPException(
            error.status_code, detail={"code": error.code, "message": error.message}
        ) from error


@router.get("", response_model=list[ChatSnapshot])
def list_chats(service: Service):
    return _call(service.list)


@router.post("", response_model=ChatAccess, status_code=201)
def create_chat(request: ChatCreate, service: Service):
    return _call(service.create, request)


@router.post("/invites/preview", response_model=InvitePreview, response_model_exclude_none=True)
def preview_invite(request: InviteToken, service: Service):
    return _call(service.preview, request.invite_token)


@router.post("/join", response_model=ChatSnapshot)
def join_chat(request: ChatJoin, service: Service):
    return _call(service.join, request)


@router.get("/{chat_id}", response_model=ChatSnapshot)
def read_chat(chat_id: UUID, service: Service):
    return _call(service.get, chat_id)


@router.post("/{chat_id}/invite", response_model=ChatAccess)
def rotate_invite(chat_id: UUID, request: ChatCommand, service: Service):
    return _call(service.rotate_invite, chat_id, request)


@router.post("/{chat_id}/invite/revoke", response_model=ChatSnapshot)
def revoke_invite(chat_id: UUID, request: ChatCommand, service: Service):
    return _call(service.revoke_invite, chat_id, request)


@router.post("/{chat_id}/leave", response_model=ChatSnapshot)
def leave_chat(chat_id: UUID, request: ChatCommand, service: Service):
    return _call(service.leave, chat_id, request)


@router.post("/{chat_id}/block", response_model=ChatSnapshot)
def block_chat(chat_id: UUID, request: ChatCommand, service: Service):
    return _call(service.block, chat_id, request)


@router.post("/{chat_id}/report", response_model=ChatSnapshot)
def report_chat(chat_id: UUID, request: ReportChat, service: Service):
    return _call(service.report, chat_id, request)


@router.post("/{chat_id}/rounds", response_model=ChatSnapshot, status_code=201)
def start_round(chat_id: UUID, request: StartChatRound, service: Service):
    return _call(service.start_round, chat_id, request)


@router.post("/{chat_id}/rounds/{round_id}/retry", response_model=ChatSnapshot)
def retry_photo(chat_id: UUID, round_id: UUID, request: ChatCommand, service: Service):
    return _call(service.retry, chat_id, round_id, request)


@router.post("/{chat_id}/rounds/{round_id}/target", response_model=ChatSnapshot)
def select_target(chat_id: UUID, round_id: UUID, request: SelectChatTarget, service: Service):
    return _call(service.select_target, chat_id, round_id, request)


@router.post("/{chat_id}/rounds/{round_id}/clue", response_model=ChatSnapshot)
def send_clue(chat_id: UUID, round_id: UUID, request: SendChatClue, service: Service):
    return _call(service.clue, chat_id, round_id, request)


@router.post("/{chat_id}/rounds/{round_id}/suggest", response_model=ChatSuggestion)
def suggest_clue(chat_id: UUID, round_id: UUID, request: ChatCommand, service: Service):
    return _call(service.suggest, chat_id, round_id, request)


@router.post("/{chat_id}/rounds/{round_id}/guess", response_model=ChatSnapshot)
def guess_target(chat_id: UUID, round_id: UUID, request: GuessChatTarget, service: Service):
    return _call(service.guess, chat_id, round_id, request)


@router.post("/{chat_id}/rounds/{round_id}/reveal", response_model=ChatSnapshot)
def reveal_answer(chat_id: UUID, round_id: UUID, request: ChatCommand, service: Service):
    return _call(service.reveal, chat_id, round_id, request)


@router.post("/{chat_id}/rounds/{round_id}/cancel", response_model=ChatSnapshot)
def cancel_round(chat_id: UUID, round_id: UUID, request: ChatCommand, service: Service):
    return _call(service.cancel, chat_id, round_id, request)


@router.post("/{chat_id}/rounds/{round_id}/help", response_model=ChatHelp)
def private_help(chat_id: UUID, round_id: UUID, service: Service):
    return _call(service.help, chat_id, round_id)


@router.get("/{chat_id}/rounds/{round_id}/image")
def round_image(
    chat_id: UUID, round_id: UUID, service: Service, width: Annotated[int, Query()] = 640
):
    if width not in {320, 640, 1280}:
        raise HTTPException(
            422,
            detail={"code": "invalid_width", "message": "Width must be one of 320, 640 or 1280."},
        )
    data = _call(service.image, chat_id, round_id, width)
    return Response(
        content=data,
        media_type="image/webp",
        headers={
            "Cache-Control": "private, no-store",
            "Vary": "Authorization",
            "X-Content-Type-Options": "nosniff",
        },
    )
