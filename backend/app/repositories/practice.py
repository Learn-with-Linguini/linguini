"""Session repository errors shared by the workflow service and persistence layer."""


class PracticeStorageError(Exception):
    pass


class PracticeNotFoundError(Exception):
    pass


class PracticeConflictError(Exception):
    pass


class ActiveSessionExistsError(PracticeConflictError):
    def __init__(self, message: str, active_session_id) -> None:
        super().__init__(message)
        self.active_session_id = active_session_id


class ActiveSessionLimitReachedError(PracticeConflictError):
    pass


class DailyLessonLimitReachedError(PracticeConflictError):
    """The user has reached their tier's daily photo lesson limit."""


INSUFFICIENT_SCENE_MESSAGE = (
    "This photo doesn't have enough for Linguini to check a lesson yet. "
    "Add more objects, counts, adjectives or connections, or try another photo."
)


class InsufficientSceneError(PracticeConflictError):
    """No mission can be checked from the confirmed scene, so the review is not saved."""

    def __init__(self, shortfall) -> None:
        super().__init__(INSUFFICIENT_SCENE_MESSAGE)
        self.shortfall = shortfall


class ClueNamesTargetError(Exception):
    """A described I-Spy clue uses the word for the object it describes."""
