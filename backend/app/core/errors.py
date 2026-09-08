class CaptureError(Exception):
    pass


class SsrfBlockedError(CaptureError):
    pass


class NotFoundError(ValueError):
    pass


class ValidationError(ValueError):
    pass


class ConflictError(ValueError):
    pass
