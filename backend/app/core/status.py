from typing import Final

STATUS_NEVER_CHECKED: Final = "Never Checked"
STATUS_CHECKING: Final = "Checking"
STATUS_OK: Final = "OK"
STATUS_CHANGED: Final = "Changed"
STATUS_FAILED: Final = "Failed"
STATUS_ACKNOWLEDGED: Final = "Acknowledged"
STATUS_AVAILABILITY_ISSUE: Final = "Availability Issue"
STATUS_DEFACED: Final = "Defaced"

ALL_TARGET_STATUSES: Final = {
    STATUS_NEVER_CHECKED,
    STATUS_CHECKING,
    STATUS_OK,
    STATUS_CHANGED,
    STATUS_FAILED,
    STATUS_ACKNOWLEDGED,
    STATUS_AVAILABILITY_ISSUE,
    STATUS_DEFACED,
}

ALLOWED_TARGET_STATUS_TRANSITIONS: Final = {
    STATUS_NEVER_CHECKED: {STATUS_CHECKING},
    STATUS_CHECKING: {STATUS_OK, STATUS_CHANGED, STATUS_FAILED, STATUS_AVAILABILITY_ISSUE},
    STATUS_OK: {STATUS_CHECKING},
    STATUS_CHANGED: {STATUS_CHECKING, STATUS_ACKNOWLEDGED, STATUS_DEFACED, STATUS_OK},
    STATUS_ACKNOWLEDGED: {STATUS_CHECKING, STATUS_DEFACED, STATUS_OK},
    STATUS_DEFACED: {STATUS_CHECKING, STATUS_OK, STATUS_ACKNOWLEDGED},
    STATUS_FAILED: {STATUS_CHECKING, STATUS_OK},
    STATUS_AVAILABILITY_ISSUE: {STATUS_CHECKING, STATUS_OK},
}


class InvalidStatusTransitionError(ValueError):
    pass


def is_valid_transition(current_status: str, next_status: str) -> bool:
    if current_status == next_status and current_status in ALL_TARGET_STATUSES:
        return True
    return next_status in ALLOWED_TARGET_STATUS_TRANSITIONS.get(current_status, set())


def require_valid_transition(current_status: str, next_status: str) -> None:
    if not is_valid_transition(current_status, next_status):
        raise InvalidStatusTransitionError(
            f"Invalid target status transition: {current_status!r} -> {next_status!r}"
        )
