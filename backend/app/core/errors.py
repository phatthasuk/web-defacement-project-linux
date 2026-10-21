class CaptureError(Exception):
    pass


class CaptureBudgetExceeded(CaptureError):
    """A page used more network, DOM or screenshot resources than allowed."""


class ScreenshotCaptureError(CaptureError):
    """Chromium failed to capture a screenshot for a potentially transient reason."""


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
