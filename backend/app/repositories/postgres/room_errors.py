"""Public errors for private rooms and friends."""


class RoomError(Exception):
    def __init__(self, code, message, status_code=409):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code
