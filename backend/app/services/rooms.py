"""Coordinate durable room commands and claimed photo jobs outside transactions."""

import logging

from app.repositories.postgres.rooms import RoomError
from app.services.background import InlineBackgroundRunner
from app.services.room_photos import RoomPhotoError

logger = logging.getLogger(__name__)


class RoomService:
    def __init__(self, repository, photo_preparer, background=None, *, image_reader=None):
        self.repository = repository
        self.photo_preparer = photo_preparer
        self.background = background or InlineBackgroundRunner()
        self.image_reader = image_reader

    def create(self, request):
        return self.repository.create(request)

    def join(self, request):
        return self.repository.join(request)

    def get(self, room_id):
        snapshot = self.repository.get(room_id)
        self._schedule(snapshot)
        return self.repository.get(room_id)

    def active(self):
        snapshot = self.repository.active()
        if snapshot:
            self._schedule(snapshot)
            return self.repository.get(snapshot.id)
        return None

    def add_photo(self, room_id, request):
        snapshot = self.repository.add_photo(room_id, request)
        self._schedule(snapshot)
        return self.repository.get(room_id)

    def remove_photo(self, room_id, photo_id, request):
        return self.repository.remove_photo(room_id, photo_id, request)

    def review_photo(self, room_id, photo_id, request):
        snapshot = self.repository.review_photo(room_id, photo_id, request)
        self._schedule(snapshot)
        return self.repository.get(room_id)

    def retry_photo(self, room_id, photo_id, request):
        snapshot = self.repository.retry_photo(room_id, photo_id, request)
        self._schedule(snapshot)
        return self.repository.get(room_id)

    def ready(self, room_id, request):
        return self.repository.ready(room_id, request)

    def start(self, room_id, request):
        return self.repository.start(room_id, request)

    def clue(self, room_id, turn_id, request):
        return self.repository.clue(room_id, turn_id, request)

    def guess(self, room_id, turn_id, request):
        return self.repository.guess(room_id, turn_id, request)

    def acknowledge(self, room_id, turn_id, request):
        return self.repository.acknowledge(room_id, turn_id, request)

    def leave(self, room_id, request):
        return self.repository.leave(room_id, request)

    def authorized_photo_asset(self, user_id, room_id, photo_id):
        return self.repository.authorized_photo_asset(user_id, room_id, photo_id)

    def read_image(self, room_id, photo_id, width):
        asset = self.authorized_photo_asset(self.repository.user_id, room_id, photo_id)
        if self.image_reader is None:
            raise RoomError("room_photo_unavailable", "Photo preview is unavailable.", 503)
        return self.image_reader(asset, width)

    def _schedule(self, snapshot):
        if snapshot.status != "lobby":
            return
        for photo in snapshot.photos:
            if (
                photo.owner_user_id != self.repository.user_id
                or photo.processing
                or photo.status not in {"queued", "preparing"}
            ):
                continue
            try:
                job = self.repository.claim_photo(snapshot.id, photo.id)
                if job:
                    try:
                        self.background.submit(self._run_photo, job)
                    except Exception:
                        self.repository.finish_photo(
                            job,
                            error=RoomPhotoError(
                                "room_photo_unavailable",
                                "Photo preparation could not start. Try again.",
                            ),
                        )
            except RoomError as error:
                if error.code not in {
                    "room_not_found",
                    "room_not_active",
                    "room_conflict",
                    "room_photo_not_found",
                }:
                    raise

    def _run_photo(self, job):
        try:
            if self.photo_preparer is None:
                raise RoomPhotoError("room_photo_unavailable", "Photo preparation is unavailable.")
            if job.phase == "analysis":
                result = self.photo_preparer.analyze(
                    job.photo_id,
                    job.owner_user_id,
                    job.asset,
                    job.profile,
                )
            else:
                result = self.photo_preparer.build_pack(
                    job.photo_id,
                    job.owner_user_id,
                    job.profile,
                    job.analysis,
                    job.review,
                )
            self.repository.finish_photo(job, result=result)
        except RoomPhotoError as error:
            self.repository.finish_photo(job, error=error)
        except RoomError as error:
            # A removed member or deleted account must not recreate its photo.
            logger.info("Room photo job stopped: %s", error.code)
        except Exception:
            logger.exception("Room photo preparation failed.")
            self.repository.finish_photo(
                job,
                error=RoomPhotoError(
                    "room_photo_unavailable",
                    "Photo preparation did not finish. Try again.",
                ),
            )
