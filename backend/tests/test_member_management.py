import secrets
from collections.abc import Callable
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session as DbSession

from app.api.deps import hash_token
from app.core.security import get_password_hash
from app.core.time import utcnow
from app.main import app
from app.models.member import UserTargetAssignment
from app.models.session import Session as AuthSession
from app.models.target import Target
from app.models.user import User


async def test_registration_requires_admin_approval_and_creates_no_session(
    unauth_client: httpx.AsyncClient,
    client: httpx.AsyncClient,
    api_session_factory: Callable[[], DbSession],
    auth_credentials: dict[str, str],
) -> None:
    response = await unauth_client.post(
        "/auth/register",
        headers={"Origin": "http://testserver"},
        json={
            "username": "pending-operator",
            "display_name": "Pending Operator",
            "password": "a safe password longer than twelve",
            "password_confirmation": "a safe password longer than twelve",
        },
    )
    assert response.status_code == 201
    with api_session_factory() as db:
        member = db.query(User).filter_by(username="pending-operator").one()
        assert member.role == "operator"
        assert member.registration_status == "pending"
        assert member.is_active is False
        assert db.query(AuthSession).filter_by(user_id=member.id).count() == 0
        member_id = member.id

    assert (
        await unauth_client.post(
            "/auth/login",
            json={"username": "pending-operator", "password": "a safe password longer than twelve"},
        )
    ).status_code == 401
    approved = await client.post(f"/members/{member_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "active"
    with api_session_factory() as db:
        member = db.get(User, member_id)
        assert member is not None
        assert member.registration_reviewed_by == int(auth_credentials["user_id"])
        assert member.registration_reviewed_at is not None


async def test_operator_target_scope_is_applied_to_list_and_direct_ids(
    client: httpx.AsyncClient,
    api_session_factory: Callable[[], DbSession],
) -> None:
    now = utcnow()
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    with api_session_factory() as db:
        operator = User(
            username="scoped-operator",
            display_name="Scoped Operator",
            hashed_password=get_password_hash("a sufficiently long password"),
            is_active=True,
            role="operator",
            registration_status="approved",
        )
        visible = Target(name="Assigned", url="https://93.184.216.34", is_active=True, status="OK")
        hidden = Target(name="Unassigned", url="https://1.1.1.1", is_active=True, status="OK")
        db.add_all([operator, visible, hidden])
        db.flush()
        db.add(UserTargetAssignment(user_id=operator.id, target_id=visible.id, assigned_at=now))
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
        visible_id, hidden_id = visible.id, hidden.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"session_id": raw_token},
        headers={"X-CSRF-Token": csrf_token},
    ) as operator_client:
        result = await operator_client.get("/targets/page")
        assert result.status_code == 200
        assert [item["id"] for item in result.json()["items"]] == [visible_id]
        assert (await operator_client.get(f"/targets/{hidden_id}")).status_code == 404
        assert (await operator_client.get("/members")).status_code == 403

async def test_member_utc_serialization_and_batched_queries(
    client: httpx.AsyncClient,
    api_session_factory: Callable[[], DbSession],
) -> None:
    now = utcnow()
    with api_session_factory() as db:
        op1 = User(
            username="batch-op-1",
            display_name="Batch Op 1",
            hashed_password=get_password_hash("password123456"),
            is_active=True,
            role="operator",
            registration_status="approved",
            created_at=now,
        )
        op2 = User(
            username="batch-op-2",
            display_name="Batch Op 2",
            hashed_password=get_password_hash("password123456"),
            is_active=True,
            role="operator",
            registration_status="approved",
            created_at=now,
        )
        site1 = Target(
            name="Batch Site 1", url="https://site1.example.com", is_active=True, status="OK"
        )
        site2 = Target(
            name="Batch Site 2", url="https://site2.example.com", is_active=True, status="OK"
        )
        db.add_all([op1, op2, site1, site2])
        db.flush()
        db.add(UserTargetAssignment(user_id=op1.id, target_id=site1.id, assigned_at=now))
        db.add(UserTargetAssignment(user_id=op1.id, target_id=site2.id, assigned_at=now))
        db.add(UserTargetAssignment(user_id=op2.id, target_id=site1.id, assigned_at=now))
        db.commit()

    res = await client.get("/members?limit=50")
    assert res.status_code == 200
    data = res.json()
    items = {item["username"]: item for item in data["items"]}
    assert "batch-op-1" in items
    assert "batch-op-2" in items
    assert items["batch-op-1"]["assigned_website_count"] == 2
    assert items["batch-op-2"]["assigned_website_count"] == 1
    assert items["batch-op-1"]["registration_at"].endswith("Z")
    assert items["batch-op-1"]["created_at"].endswith("Z")

    res2 = await client.get("/member-assignments/websites?search=Batch+Site+1")
    assert res2.status_code == 200
    websites = res2.json()["items"]
    assert len(websites) == 1
    assignee_names = {a["username"] for a in websites[0]["assignees"]}
    assert assignee_names == {"batch-op-1", "batch-op-2"}

