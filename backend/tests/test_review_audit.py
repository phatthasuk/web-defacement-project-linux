"""Review and baseline decisions must leave an audit event naming who made them."""

import json
import secrets
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from conftest import write_capture
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import get_capture_func, hash_token
from app.core.config import Settings
from app.core.security import get_password_hash
from app.core.status import STATUS_AWAITING_BASELINE
from app.core.time import utcnow
from app.main import app
from app.models import MemberAuditEvent, Snapshot, Target, User
from app.models.session import Session as AuthSession
from app.services.capture.capture import CaptureResult
from app.services.review import approve_baseline

REVIEW_ACTIONS = ("baseline.", "check.")


async def _create_target(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/targets", json={"name": f"Target {uuid4()}", "url": "https://93.184.216.34"}
    )
    assert response.status_code == 201
    return response.json()["id"]


def _queue_captures(captures: list[tuple[str, str, str]]) -> None:
    async def queued(url: str, settings, out_dir: Path) -> CaptureResult:
        snapshot_id, text, color = captures.pop(0)
        return write_capture(out_dir, snapshot_id, text, color)

    app.dependency_overrides[get_capture_func] = lambda: queued


async def _review_events(client: httpx.AsyncClient, target_id: str) -> list[dict]:
    response = await client.get("/audit-events", params={"target_id": target_id, "limit": 200})
    assert response.status_code == 200
    events = [e for e in response.json() if e["action"].startswith(REVIEW_ACTIONS)]
    return list(reversed(events))  # oldest first


async def _changed_target(client: httpx.AsyncClient) -> tuple[str, str, str]:
    """A target with one approved baseline and one unacknowledged Changed check."""
    target_id = await _create_target(client)
    _queue_captures([("baseline", "Hello", "white"), ("current", "Changed", "black")])
    await client.post(f"/targets/{target_id}/check")
    first = (await client.get(f"/targets/{target_id}/snapshots")).json()[0]["id"]
    approved = await client.post(
        f"/targets/{target_id}/baseline/approve", json={"snapshot_id": first}
    )
    assert approved.status_code == 200
    await client.post(f"/targets/{target_id}/check")
    check = (await client.get(f"/targets/{target_id}/checks")).json()[0]
    return target_id, first, check["id"]


async def test_review_and_baseline_decisions_are_audited_with_the_actor(
    client: httpx.AsyncClient, auth_credentials: dict[str, str]
) -> None:
    target_id, first_snapshot, check_id = await _changed_target(client)
    current_snapshot = (await client.get(f"/targets/{target_id}/checks")).json()[0][
        "current_snapshot_id"
    ]

    assert (await client.post(f"/checks/{check_id}/ack")).status_code == 200
    approve = await client.post(
        f"/targets/{target_id}/baseline/approve", json={"snapshot_id": current_snapshot}
    )
    assert approve.status_code == 200
    demote = await client.post(f"/targets/{target_id}/baselines/{first_snapshot}/demote")
    assert demote.status_code == 200

    events = await _review_events(client, target_id)

    assert [e["action"] for e in events] == [
        "baseline.approved",
        "check.acknowledged",
        "baseline.approved",
        "baseline.demoted",
    ]
    admin_id = int(auth_credentials["user_id"])
    assert {e["actor_id"] for e in events} == {admin_id}
    assert all(e["target_id"] == target_id for e in events)

    first_approval, ack, second_approval, demotion = events
    assert first_approval["before"]["is_baseline"] is False
    assert first_approval["after"]["baseline_ids"] == [first_snapshot]
    assert ack["before"] == {
        "check_id": check_id,
        "acknowledged": False,
        "target_status": "Changed",
    }
    assert ack["after"]["acknowledged"] is True
    assert ack["after"]["target_status"] == "Acknowledged"
    assert second_approval["before"]["baseline_ids"] == [first_snapshot]
    assert set(second_approval["after"]["baseline_ids"]) == {first_snapshot, current_snapshot}
    assert second_approval["after"]["target_status"] == "OK"
    assert demotion["before"]["snapshot_id"] == first_snapshot
    assert demotion["before"]["is_baseline"] is True
    assert demotion["after"]["is_baseline"] is False
    assert demotion["after"]["baseline_count"] == 1


async def test_confirming_defacement_is_audited(
    client: httpx.AsyncClient, auth_credentials: dict[str, str]
) -> None:
    target_id, _first, check_id = await _changed_target(client)

    assert (await client.post(f"/checks/{check_id}/confirm-defaced")).status_code == 200

    events = await _review_events(client, target_id)
    (event,) = (e for e in events if e["action"] == "check.defacement_confirmed")
    assert event["actor_id"] == int(auth_credentials["user_id"])
    assert event["before"]["target_status"] == "Changed"
    assert event["before"]["acknowledged"] is False
    assert event["after"]["target_status"] == "Defaced"
    assert event["after"]["acknowledged"] is True


async def test_baseline_cap_demotions_are_audited_as_caused_by_the_approval(
    client: httpx.AsyncClient, auth_credentials: dict[str, str]
) -> None:
    target_id, first_snapshot, check_id = await _changed_target(client)
    current_snapshot = (await client.get(f"/targets/{target_id}/checks")).json()[0][
        "current_snapshot_id"
    ]
    one_baseline = Settings(MAX_BASELINES_PER_TARGET=1)

    # The route lets the service read settings itself, so patch it there.
    with patch("app.services.review.get_settings", return_value=one_baseline):
        approve = await client.post(
            f"/targets/{target_id}/baseline/approve", json={"snapshot_id": current_snapshot}
        )
    assert approve.status_code == 200

    events = await _review_events(client, target_id)
    (cap_event,) = (e for e in events if e["source"] == "baseline_cap")
    assert cap_event["action"] == "baseline.demoted"
    assert cap_event["actor_id"] == int(auth_credentials["user_id"])
    assert cap_event["before"] == {"snapshot_id": first_snapshot, "is_baseline": True}
    assert cap_event["after"]["caused_by_snapshot_id"] == current_snapshot
    approval = [e for e in events if e["action"] == "baseline.approved"][-1]
    assert approval["after"]["baseline_ids"] == [current_snapshot]


async def test_audit_events_contain_ids_and_states_but_never_urls(
    client: httpx.AsyncClient,
) -> None:
    target_id, _first, check_id = await _changed_target(client)
    await client.post(f"/checks/{check_id}/ack")

    events = await _review_events(client, target_id)

    serialised = json.dumps(events)
    assert events
    assert "http" not in serialised
    assert "93.184.216.34" not in serialised


async def test_acknowledging_twice_records_only_the_real_change(
    client: httpx.AsyncClient,
) -> None:
    target_id, _first, check_id = await _changed_target(client)

    await client.post(f"/checks/{check_id}/ack")
    await client.post(f"/checks/{check_id}/ack")

    events = await _review_events(client, target_id)
    assert [e["action"] for e in events].count("check.acknowledged") == 1


async def test_failed_commit_leaves_no_success_event(
    api_session_factory: Callable[[], DbSession],
) -> None:
    with api_session_factory() as db:
        target = Target(
            name="Rollback", url="https://93.184.216.34", status=STATUS_AWAITING_BASELINE
        )
        db.add(target)
        db.flush()
        snapshot = Snapshot(
            target_id=target.id,
            final_url="https://93.184.216.34",
            http_status=200,
            screenshot_path="s.png",
            text_path="t.txt",
            html_path="h.html",
            url_revision=target.url_revision,
        )
        db.add(snapshot)
        actor = User(
            username="actor",
            hashed_password="x",
            is_active=True,
            role="admin",
        )
        db.add(actor)
        db.commit()
        target_id, snapshot_id = target.id, snapshot.id

        with patch.object(db, "commit", side_effect=RuntimeError("disk full")):
            with pytest.raises(RuntimeError):
                approve_baseline(db, target_id, snapshot_id, actor=actor)
        db.rollback()

        events = db.scalar(
            select(func.count())
            .select_from(MemberAuditEvent)
            .where(MemberAuditEvent.action.like("baseline.%"))
        )
        assert events == 0
        assert db.get(Snapshot, snapshot_id).is_baseline is False


async def test_audit_events_are_admin_only(
    client: httpx.AsyncClient,
    api_session_factory: Callable[[], DbSession],
    unauth_client: httpx.AsyncClient,
) -> None:
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now = utcnow()
    with api_session_factory() as db:
        operator = User(
            username="audit-operator",
            hashed_password=get_password_hash("a sufficiently long password"),
            is_active=True,
            role="operator",
            registration_status="approved",
        )
        db.add(operator)
        db.flush()
        db.add(
            AuthSession(
                token_hash=hash_token(raw_token),
                user_id=operator.id,
                csrf_token=csrf_token,
                created_at=now,
                last_seen_at=now,
                absolute_expires_at=now + timedelta(days=14),
                idle_expires_at=now + timedelta(days=1),
            )
        )
        db.commit()

    assert (await client.get("/audit-events")).status_code == 200
    assert (await unauth_client.get("/audit-events")).status_code == 401
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        cookies={"session_id": raw_token},
        headers={"X-CSRF-Token": csrf_token},
    ) as operator_client:
        assert (await operator_client.get("/audit-events")).status_code == 403
