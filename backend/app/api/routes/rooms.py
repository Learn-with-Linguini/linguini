"""Authenticated invite-only photo rooms; the dependency owns feature gating."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.dependencies import get_room_service
from app.repositories.postgres.rooms import RoomError
from app.schemas.rooms import (
    AddRoomPhotoRequest,
    CreateRoomRequest,
    JoinRoomRequest,
    ReviewRoomPhotoRequest,
    RoomAccessResponse,
    RoomClueRequest,
    RoomCommand,
    RoomGuessRequest,
    RoomReadyRequest,
    RoomSnapshot,
)
from app.services.rooms import RoomService

router = APIRouter(prefix="/rooms", tags=["rooms"])
RoomServiceDep = Annotated[RoomService, Depends(get_room_service)]


def _call(fn, *args):
    try:
        return fn(*args)
    except RoomError as error:
        raise HTTPException(
            error.status_code,
            detail={
                "code": error.code,
                "message": error.message,
            },
        ) from error


@router.post("", response_model=RoomAccessResponse, status_code=201)
def create_room(request: CreateRoomRequest, service: RoomServiceDep):
    return _call(service.create, request)


@router.post("/join", response_model=RoomAccessResponse)
def join_room(request: JoinRoomRequest, service: RoomServiceDep):
    return _call(service.join, request)


@router.get("/active", response_model=RoomSnapshot | None)
def active_room(service: RoomServiceDep):
    return _call(service.active)


@router.get("/{room_id}", response_model=RoomSnapshot)
def get_room(room_id: UUID, service: RoomServiceDep):
    return _call(service.get, room_id)


@router.post("/{room_id}/photos", response_model=RoomSnapshot)
def add_photo(room_id: UUID, request: AddRoomPhotoRequest, service: RoomServiceDep):
    return _call(service.add_photo, room_id, request)


@router.post("/{room_id}/photos/{photo_id}/remove", response_model=RoomSnapshot)
def remove_photo(room_id: UUID, photo_id: UUID, request: RoomCommand, service: RoomServiceDep):
    return _call(service.remove_photo, room_id, photo_id, request)


@router.post("/{room_id}/photos/{photo_id}/review", response_model=RoomSnapshot)
def review_photo(
    room_id: UUID, photo_id: UUID, request: ReviewRoomPhotoRequest, service: RoomServiceDep
):
    return _call(service.review_photo, room_id, photo_id, request)


@router.post("/{room_id}/photos/{photo_id}/retry", response_model=RoomSnapshot)
def retry_photo(room_id: UUID, photo_id: UUID, request: RoomCommand, service: RoomServiceDep):
    return _call(service.retry_photo, room_id, photo_id, request)


@router.get("/{room_id}/photos/{photo_id}/image")
def room_photo_image(
    room_id: UUID,
    photo_id: UUID,
    service: RoomServiceDep,
    width: Annotated[Literal[320, 640, 1280], Query()] = 640,
):
    data = _call(service.read_image, room_id, photo_id, width)
    return Response(
        content=data,
        media_type="image/webp",
        headers={
            "Cache-Control": "private, no-store",
            "Vary": "Authorization",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{room_id}/ready", response_model=RoomSnapshot)
def ready_room(room_id: UUID, request: RoomReadyRequest, service: RoomServiceDep):
    return _call(service.ready, room_id, request)


@router.post("/{room_id}/start", response_model=RoomSnapshot)
def start_room(room_id: UUID, request: RoomCommand, service: RoomServiceDep):
    return _call(service.start, room_id, request)


@router.post("/{room_id}/turns/{turn_id}/clue", response_model=RoomSnapshot)
def send_clue(room_id: UUID, turn_id: UUID, request: RoomClueRequest, service: RoomServiceDep):
    return _call(service.clue, room_id, turn_id, request)


@router.post("/{room_id}/turns/{turn_id}/guess", response_model=RoomSnapshot)
def send_guess(room_id: UUID, turn_id: UUID, request: RoomGuessRequest, service: RoomServiceDep):
    return _call(service.guess, room_id, turn_id, request)


@router.post("/{room_id}/turns/{turn_id}/ack", response_model=RoomSnapshot)
def acknowledge_round(room_id: UUID, turn_id: UUID, request: RoomCommand, service: RoomServiceDep):
    return _call(service.acknowledge, room_id, turn_id, request)


@router.post("/{room_id}/leave", response_model=RoomSnapshot)
def leave_room(room_id: UUID, request: RoomCommand, service: RoomServiceDep):
    return _call(service.leave, room_id, request)
