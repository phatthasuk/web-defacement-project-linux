class CaptureError(Exception):
    pass


class DnsResolutionError(CaptureError):
    pass


class SsrfBlockedError(CaptureError):
    pass


class NotFoundError(ValueError):
    pass


class ValidationError(ValueError):
    pass


class ConflictError(ValidationError):
    pass


class UpstreamConnectionError(CaptureError):
    """The capture proxy could not open a socket to an allowed destination."""
