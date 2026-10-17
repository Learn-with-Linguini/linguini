"""Authenticated, private friend invitations without account search."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import get_friend_repository
from app.api.routes.rooms import _call
from app.repositories.postgres.friends import PostgresFriendRepository
from app.schemas.friends import FriendAcceptRequest, FriendInvite, FriendInviteRequest, FriendPublic

router = APIRouter(prefix="/friends", tags=["friends"])
FriendsDep = Annotated[PostgresFriendRepository, Depends(get_friend_repository)]


@router.get("", response_model=list[FriendPublic])
def list_friends(repository: FriendsDep):
    return _call(repository.list)


@router.post("/invite", response_model=FriendInvite, status_code=201)
def invite_friend(request: FriendInviteRequest, repository: FriendsDep):
    return _call(repository.invite, request)


@router.post("/accept", response_model=FriendPublic)
def accept_friend(request: FriendAcceptRequest, repository: FriendsDep):
    return _call(repository.accept, request)


@router.delete("/{user_id}", status_code=204)
def remove_friend(user_id: UUID, repository: FriendsDep):
    _call(repository.remove, user_id)
    return Response(status_code=204)
