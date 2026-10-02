from app.repositories.learning import LearningRepository
from app.schemas.base import CursorPage
from app.schemas.progress import ProgressResponse
from app.schemas.vocabulary import DailyVocabularyItem
from app.services.users import UserService


class ProgressNotFoundError(Exception):
    pass


class InvalidCursorError(Exception):
    pass


class LearningService:
    def __init__(self, repository: LearningRepository, users: UserService) -> None:
        self.repository = repository
        self.users = users

    def get_progress(self, language_code: str | None = None) -> ProgressResponse:
        user = self.users.get_current_user()
        data = self.repository.get_progress(user.id, language_code, user.timezone)
        if data is None:
            if (
                language_code is not None
                and self.repository.get_progress(user.id, timezone=user.timezone) is not None
            ):
                return ProgressResponse(xp=0, scenarios=[], leaderboard=[])
            raise ProgressNotFoundError("No progress found for this user.")
        board = [
            row.model_copy(update={"name": user.display_name, "xp": data.xp})
            if row.is_you
            else row.model_copy()
            for row in data.leaderboard
        ]
        board.sort(key=lambda row: row.xp, reverse=True)
        for rank, row in enumerate(board, 1):
            row.rank = rank
        return ProgressResponse(
            xp=data.xp,
            scenarios=data.scenarios,
            leaderboard=board,
            streak=data.streak,
        )

    def list_vocabulary(
        self, cursor: str | None, limit: int, language_code: str | None = None
    ) -> CursorPage[DailyVocabularyItem]:
        user = self.users.get_current_user()
        rows = self.repository.list_vocabulary(user.id)
        if language_code is not None:
            rows = [row for row in rows if row.vocabulary.language_code.lower() == language_code]
        offset = 0
        if cursor is not None:
            index = next(
                (i for i, row in enumerate(rows) if str(row.vocabulary.id) == cursor), None
            )
            if index is None:
                raise InvalidCursorError("Invalid vocabulary cursor.")
            offset = index + 1
        page = rows[offset : offset + limit]
        next_cursor = str(page[-1].vocabulary.id) if offset + limit < len(rows) else None
        return CursorPage(items=page, next_cursor=next_cursor)
