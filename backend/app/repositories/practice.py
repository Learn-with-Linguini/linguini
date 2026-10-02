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
