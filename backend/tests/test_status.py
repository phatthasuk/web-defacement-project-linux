from app.core.status import (
    STATUS_ACKNOWLEDGED,
    STATUS_AVAILABILITY_ISSUE,
    STATUS_CHANGED,
    STATUS_CHECKING,
    STATUS_DEFACED,
    STATUS_FAILED,
    STATUS_NEVER_CHECKED,
    STATUS_OK,
    is_valid_transition,
)


def test_target_status_allows_expected_transitions():
    legal_transitions = [
        (STATUS_NEVER_CHECKED, STATUS_CHECKING),
        (STATUS_CHECKING, STATUS_OK),
        (STATUS_CHECKING, STATUS_CHANGED),
        (STATUS_CHECKING, STATUS_FAILED),
        (STATUS_CHECKING, STATUS_AVAILABILITY_ISSUE),
        (STATUS_OK, STATUS_CHECKING),
        (STATUS_CHANGED, STATUS_CHECKING),
        (STATUS_CHANGED, STATUS_ACKNOWLEDGED),
        (STATUS_CHANGED, STATUS_DEFACED),
        (STATUS_CHANGED, STATUS_OK),
        (STATUS_ACKNOWLEDGED, STATUS_CHECKING),
        (STATUS_ACKNOWLEDGED, STATUS_DEFACED),
        (STATUS_ACKNOWLEDGED, STATUS_OK),
        (STATUS_DEFACED, STATUS_CHECKING),
        (STATUS_DEFACED, STATUS_OK),
        (STATUS_DEFACED, STATUS_ACKNOWLEDGED),
        (STATUS_DEFACED, STATUS_DEFACED),
        (STATUS_FAILED, STATUS_CHECKING),
        (STATUS_AVAILABILITY_ISSUE, STATUS_CHECKING),
        (STATUS_AVAILABILITY_ISSUE, STATUS_OK),
        (STATUS_OK, STATUS_OK),
    ]

    for current_status, next_status in legal_transitions:
        assert is_valid_transition(current_status, next_status)


def test_target_status_rejects_representative_illegal_transitions():
    illegal_transitions = [
        (STATUS_NEVER_CHECKED, STATUS_OK),
        (STATUS_NEVER_CHECKED, STATUS_DEFACED),
        (STATUS_OK, STATUS_ACKNOWLEDGED),
        (STATUS_OK, STATUS_DEFACED),
        (STATUS_FAILED, STATUS_ACKNOWLEDGED),
        (STATUS_FAILED, STATUS_DEFACED),
        ("Unknown", STATUS_OK),
    ]

    for current_status, next_status in illegal_transitions:
        assert not is_valid_transition(current_status, next_status)
