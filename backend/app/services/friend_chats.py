"""Coordinate photo and language work outside chat transactions."""

import logging

from app.repositories.postgres.room_errors import RoomError
from app.schemas.friend_chats import ChatHelp, ChatSuggestion
from app.services.background import InlineBackgroundRunner
from app.services.room_photos import RoomPhotoError

logger = logging.getLogger(__name__)


class FriendChatService:
    def __init__(self, repository, content, *, background=None, image_reader=None):
        self.repository, self.content = repository, content
        self.background = background or InlineBackgroundRunner()
        self.image_reader = image_reader

    def create(self, request):
        return self.repository.create(request)

    def preview(self, token):
        return self.repository.preview(token)

    def join(self, request):
        return self.repository.join(request)

    def list(self):
        return self.repository.list()

    def get(self, chat_id):
        snapshot = self.repository.get(chat_id)
        self._schedule(snapshot)
        return self.repository.get(chat_id)

    def rotate_invite(self, chat_id, request):
        return self.repository.rotate_invite(chat_id, request)

    def revoke_invite(self, chat_id, request):
        return self.repository.revoke_invite(chat_id, request)

    def leave(self, chat_id, request):
        return self.repository.close(chat_id, request)

    def block(self, chat_id, request):
        return self.repository.close(chat_id, request, block=True)

    def report(self, chat_id, request):
        return self.repository.report(chat_id, request)

    def start_round(self, chat_id, request):
        snapshot = self.repository.start_round(chat_id, request)
        self._schedule(snapshot)
        return self.repository.get(chat_id)

    def retry(self, chat_id, round_id, request):
        snapshot = self.repository.retry(chat_id, round_id, request)
        self._schedule(snapshot)
        return self.repository.get(chat_id)

    def _schedule(self, snapshot):
        item = snapshot.active_round
        if (
            not item
            or item.sender_id != self.repository.user_id
            or item.photo_status != "analyzing"
        ):
            return
        job = self.repository.claim_photo(snapshot.id, item.id)
        if job:
            try:
                self.background.submit(self._analyze, job)
            except Exception:
                self.repository.finish_photo(
                    job, error="Photo preparation could not start. Try again."
                )

    def _analyze(self, job):
        try:
            content = self.content.analyze(job.round_id, job.owner_id, job.asset, job.profile)
            self.repository.finish_photo(job, content=content)
        except RoomPhotoError as error:
            self.repository.finish_photo(job, error=error.message, retryable=error.retryable)
        except RoomError as error:
            logger.info("Friend chat photo stopped: %s", error.code)
        except Exception:
            logger.exception("Friend chat photo analysis failed")
            self.repository.finish_photo(job, error="Photo analysis did not finish. Try again.")

    def _context(self, chat_id, round_id, request=None, *, sender, phases):
        context = self.repository.context(chat_id, round_id, sender=sender, phases=phases)
        if request and request.expected_revision != context["chat"]["revision"]:
            raise RoomError("chat_stale_revision", "The chat changed. Refresh and try again.", 409)
        return context

    def _content_call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except RoomPhotoError as error:
            raise RoomError(
                error.code, error.message, 422 if not error.retryable else 503
            ) from error

    def select_target(self, chat_id, round_id, request):
        replay, result = self.repository.replay(chat_id, f"target:{round_id}", request)
        if replay:
            return result
        ctx = self._context(
            chat_id, round_id, request, sender=True, phases={"selectingTarget", "composingClue"}
        )
        item = ctx["round"]
        if item["photo_status"] != "ready":
            raise RoomError("chat_photo_not_ready", "Wait for the photo to finish analyzing.", 409)
        target = self._content_call(
            self.content.select_target,
            item["content"],
            object_key=request.object_key,
            x=request.x,
            y=request.y,
            label=request.label,
            profile=ctx["profile"],
        )
        options = (
            self._content_call(self.content.clue_options, item["content"], target, ctx["profile"])
            if request.confirm
            else []
        )
        if (
            request.confirm
            and not target.get("region")
            and not (target.get("width") and target.get("height"))
        ):
            raise RoomError(
                "chat_target_region_missing",
                "Tap this object in the photo so its region can be checked.",
                422,
            )
        return self.repository.select_target(chat_id, round_id, request, target, options)

    def clue(self, chat_id, round_id, request):
        replay, result = self.repository.replay(chat_id, f"clue:{round_id}", request)
        if replay:
            return result
        ctx = self._context(
            chat_id, round_id, request, sender=True, phases={"composingClue", "awaitingFollowUp"}
        )
        text = self._content_call(
            self.content.validate_clue,
            request.text,
            ctx["round"]["target"],
            ctx["round"]["content"],
            ctx["profile"],
            previous_clues=ctx["previous_clues"],
        )
        return self.repository.send_clue(chat_id, round_id, request, text)

    def suggest(self, chat_id, round_id, request):
        replay, result = self.repository.replay(chat_id, f"suggest:{round_id}", request)
        if replay:
            return ChatSuggestion.model_validate(result)
        ctx = self._context(
            chat_id, round_id, request, sender=True, phases={"composingClue", "awaitingFollowUp"}
        )
        text = self._content_call(
            self.content.suggest_clue,
            ctx["round"]["content"],
            ctx["round"]["target"],
            ctx["profile"],
        )
        return ChatSuggestion.model_validate(
            self.repository.suggestion(chat_id, round_id, request, text)
        )

    def guess(self, chat_id, round_id, request):
        return self.repository.guess(chat_id, round_id, request)

    def reveal(self, chat_id, round_id, request):
        return self.repository.finish_round(chat_id, round_id, request, reveal=True)

    def cancel(self, chat_id, round_id, request):
        return self.repository.finish_round(chat_id, round_id, request)

    def help(self, chat_id, round_id):
        ctx = self._context(
            chat_id, round_id, sender=False, phases={"awaitingGuess", "awaitingFollowUp"}
        )
        clue = ctx["previous_clues"][-1] if ctx["previous_clues"] else ""
        result = self._content_call(
            self.content.private_help,
            ctx["round"]["content"],
            ctx["round"]["target"],
            clue,
            ctx["profile"],
        )
        self.repository.record_help(chat_id, round_id)
        return ChatHelp.model_validate(result)

    def image(self, chat_id, round_id, width):
        asset = self.repository.image_asset(chat_id, round_id)
        if self.image_reader is None:
            raise RoomError("chat_photo_unavailable", "Photo preview is unavailable.", 503)
        return self.image_reader(asset, width)
