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


class ClueNamesTargetError(Exception):
    """A described I-Spy clue uses the word for the object it describes."""


class ClueNotTargetLanguageError(Exception):
    """A described I-Spy clue is written in a language other than the target language."""
