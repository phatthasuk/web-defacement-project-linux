import importlib
from collections.abc import Callable
from datetime import timedelta

import httpx
import pytest
from sqlalchemy.orm import Session
from starlette.requests import Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.deps import hash_token
from app.core.security import get_password_hash, verify_password
from app.core.time import utcnow
from app.models.session import Session as AuthSession
from app.models.user import User

# --- Password storage -------------------------------------------------------


async def test_production_startup_rejects_insecure_session_cookie(monkeypatch) -> None:
    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(main_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(main_module.settings, "SESSION_COOKIE_SECURE", False)

    with pytest.raises(
        RuntimeError,
        match="Production environment must run with SESSION_COOKIE_SECURE=True",
    ):
        async with main_module.lifespan(main_module.app):
            pass


def test_password_is_stored_as_argon2_hash() -> None:
    hashed = get_password_hash("s3cret-passphrase-value")
    assert hashed.startswith("$argon2")
    assert "s3cret-passphrase-value" not in hashed
    assert verify_password("s3cret-passphrase-value", hashed)
    assert not verify_password("wrong", hashed)


def test_identical_passwords_produce_different_hashes() -> None:
    first = get_password_hash("same-password")
    second = get_password_hash("same-password")
    assert first != second
    assert verify_password("same-password", first)
    assert verify_password("same-password", second)


# --- Login success / session hashing ---------------------------------------


async def test_login_success_sets_cookie_and_returns_csrf(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
    api_session_factory: Callable[[], Session],
) -> None:
    response = await unauth_client.post(
        "/auth/login",
        json={"username": auth_credentials["username"], "password": auth_credentials["password"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "tester"
    assert body["csrf_token"]

    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "session_id=" in set_cookie

    raw_token = unauth_client.cookies.get("session_id")
    assert raw_token is not None
    with api_session_factory() as db:
        # The raw browser token is never stored; only its hash resolves a session.
        assert db.query(AuthSession).filter(AuthSession.token_hash == raw_token).first() is None
        stored = db.query(AuthSession).filter(
            AuthSession.token_hash == hash_token(raw_token)
        ).first()
        assert stored is not None
        assert stored.csrf_token == body["csrf_token"]


async def test_login_wrong_password_increments_failure(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
) -> None:
    response = await unauth_client.post(
        "/auth/login",
        json={"username": auth_credentials["username"], "password": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


# --- Enumeration ------------------------------------------------------------


async def test_failures_share_one_generic_response(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
    api_session_factory: Callable[[], Session],
) -> None:
    # Add an inactive user with a known password.
    with api_session_factory() as db:
        db.add(
            User(
                username="disabled",
                hashed_password=get_password_hash("disabled-pass-value"),
                is_active=False,
                role="authenticated-user",
            )
        )
        db.commit()

    unknown = await unauth_client.post(
        "/auth/login", json={"username": "nobody", "password": "whatever-value"}
    )
    wrong = await unauth_client.post(
        "/auth/login",
        json={"username": auth_credentials["username"], "password": "incorrect-value"},
    )
    inactive = await unauth_client.post(
        "/auth/login", json={"username": "disabled", "password": "disabled-pass-value"}
    )

    for resp in (unknown, wrong, inactive):
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Invalid username or password"}


# --- Session validation -----------------------------------------------------


async def test_me_requires_valid_cookie(unauth_client: httpx.AsyncClient) -> None:
    assert (await unauth_client.get("/auth/me")).status_code == 401


async def test_modified_token_is_rejected(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
) -> None:
    unauth_client.cookies.set("session_id", auth_credentials["session_token"] + "tampered")
    assert (await unauth_client.get("/auth/me")).status_code == 401


async def test_valid_session_resolves(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
) -> None:
    unauth_client.cookies.set("session_id", auth_credentials["session_token"])
    response = await unauth_client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["username"] == "tester"


async def test_revoked_session_rejected(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
    api_session_factory: Callable[[], Session],
) -> None:
    with api_session_factory() as db:
        session = db.query(AuthSession).first()
        assert session is not None
        session.revoked_at = utcnow()
        db.commit()
    unauth_client.cookies.set("session_id", auth_credentials["session_token"])
    assert (await unauth_client.get("/auth/me")).status_code == 401


async def test_idle_and_absolute_expiry_rejected(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
    api_session_factory: Callable[[], Session],
) -> None:
    with api_session_factory() as db:
        session = db.query(AuthSession).first()
        assert session is not None
        session.idle_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    unauth_client.cookies.set("session_id", auth_credentials["session_token"])
    assert (await unauth_client.get("/auth/me")).status_code == 401

    with api_session_factory() as db:
        session = db.query(AuthSession).first()
        assert session is not None
        session.idle_expires_at = utcnow() + timedelta(days=1)
        session.absolute_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert (await unauth_client.get("/auth/me")).status_code == 401


# --- Logout -----------------------------------------------------------------


async def test_logout_revokes_session_and_is_idempotent(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
) -> None:
    unauth_client.cookies.set("session_id", auth_credentials["session_token"])
    first = await unauth_client.post(
        "/auth/logout", headers={"X-CSRF-Token": auth_credentials["csrf_token"]}
    )
    assert first.status_code == 200

    # The old token can no longer authenticate.
    unauth_client.cookies.set("session_id", auth_credentials["session_token"])
    assert (await unauth_client.get("/auth/me")).status_code == 401

    # Logging out again does not error.
    unauth_client.cookies.set("session_id", auth_credentials["session_token"])
    second = await unauth_client.post(
        "/auth/logout", headers={"X-CSRF-Token": auth_credentials["csrf_token"]}
    )
    assert second.status_code == 200


async def test_logout_requires_csrf_token(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
) -> None:
    unauth_client.cookies.set("session_id", auth_credentials["session_token"])
    response = await unauth_client.post("/auth/logout")
    assert response.status_code == 403


# --- CSRF -------------------------------------------------------------------


async def test_mutation_without_csrf_is_rejected(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
) -> None:
    unauth_client.cookies.set("session_id", auth_credentials["session_token"])
    response = await unauth_client.post(
        "/targets", json={"name": "X", "url": "https://93.184.216.34"}
    )
    assert response.status_code == 403


async def test_mutation_with_invalid_csrf_is_rejected(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
) -> None:
    unauth_client.cookies.set("session_id", auth_credentials["session_token"])
    response = await unauth_client.post(
        "/targets",
        json={"name": "X", "url": "https://93.184.216.34"},
        headers={"X-CSRF-Token": "not-the-real-token"},
    )
    assert response.status_code == 403


async def test_mutation_with_valid_csrf_succeeds(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
) -> None:
    unauth_client.cookies.set("session_id", auth_credentials["session_token"])
    response = await unauth_client.post(
        "/targets",
        json={"name": "X", "url": "https://93.184.216.34"},
        headers={"X-CSRF-Token": auth_credentials["csrf_token"]},
    )
    assert response.status_code == 201


async def test_untrusted_origin_is_rejected(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/targets",
        json={"name": "X", "url": "https://93.184.216.34"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert response.status_code == 403


# --- Authorization boundary -------------------------------------------------


async def test_protected_endpoint_requires_authentication(
    unauth_client: httpx.AsyncClient,
) -> None:
    assert (await unauth_client.get("/targets")).status_code == 401


# --- Lockout ----------------------------------------------------------------


async def test_account_locks_after_repeated_failures(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
) -> None:
    username = auth_credentials["username"]
    for _ in range(5):
        resp = await unauth_client.post(
            "/auth/login", json={"username": username, "password": "wrong-value"}
        )
        assert resp.status_code == 401

    # Even the correct password is now rejected while the account is locked.
    locked = await unauth_client.post(
        "/auth/login", json={"username": username, "password": auth_credentials["password"]}
    )
    assert locked.status_code == 401


async def test_successful_login_resets_failure_counter(
    unauth_client: httpx.AsyncClient,
    auth_credentials: dict[str, str],
    api_session_factory: Callable[[], Session],
) -> None:
    username = auth_credentials["username"]
    for _ in range(3):
        await unauth_client.post(
            "/auth/login", json={"username": username, "password": "wrong-value"}
        )

    ok = await unauth_client.post(
        "/auth/login", json={"username": username, "password": auth_credentials["password"]}
    )
    assert ok.status_code == 200

    with api_session_factory() as db:
        user = db.query(User).filter(User.username == username).first()
        assert user is not None
        assert user.failed_login_count == 0
        assert user.locked_until is None


def test_get_client_ip_ignores_untrusted_forwarded_headers() -> None:
    from app.api.routes.auth import get_client_ip

    def make_mock_request(headers: dict[str, str], client_host: str = "127.0.0.1") -> Request:
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [
                (key.lower().encode("latin-1"), value.encode("latin-1"))
                for key, value in headers.items()
            ],
            "client": (client_host, 12345),
        }
        return Request(scope)

    # Headers sent directly to the app must never decide the rate-limit key.
    req1 = make_mock_request({"X-Forwarded-For": "203.0.113.195"})
    assert get_client_ip(req1) == "127.0.0.1"

    # A chain or X-Real-IP header has the same property.
    req2 = make_mock_request({"X-Forwarded-For": "203.0.113.195, 198.51.100.1, 10.0.0.1"})
    assert get_client_ip(req2) == "127.0.0.1"

    req3 = make_mock_request({"X-Real-IP": "198.51.100.42"})
    assert get_client_ip(req3) == "127.0.0.1"

    req4 = make_mock_request({}, client_host="192.0.2.1")
    assert get_client_ip(req4) == "192.0.2.1"


async def test_uvicorn_accepts_forwarded_client_ip_only_from_frontend_proxy() -> None:
    """Mirror the production Uvicorn proxy-header boundary without Docker."""
    observed_clients: list[str] = []

    async def inspect_client(scope, receive, send) -> None:
        observed_clients.append(scope["client"][0])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    guarded_app = ProxyHeadersMiddleware(inspect_client, trusted_hosts="172.30.0.2")
    headers = {"X-Forwarded-For": "198.51.100.20"}

    trusted_transport = httpx.ASGITransport(app=guarded_app, client=("172.30.0.2", 12345))
    async with httpx.AsyncClient(
        transport=trusted_transport, base_url="http://testserver"
    ) as client:
        assert (await client.get("/", headers=headers)).status_code == 204

    untrusted_transport = httpx.ASGITransport(app=guarded_app, client=("172.30.0.99", 12345))
    async with httpx.AsyncClient(
        transport=untrusted_transport, base_url="http://testserver"
    ) as client:
        assert (await client.get("/", headers=headers)).status_code == 204

    assert observed_clients == ["198.51.100.20", "172.30.0.99"]


async def test_login_rate_limit_cannot_be_bypassed_with_forwarded_headers() -> None:
    """A direct caller gets one bucket even when it changes spoofed headers."""
    from app.api.routes.auth import limiter
    from app.main import app

    limiter.reset()
    original_enabled = limiter.enabled
    limiter.enabled = True
    transport = httpx.ASGITransport(app=app, client=("192.0.2.10", 12345))
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as test_client:
            responses = [
                await test_client.post(
                    "/auth/login",
                    json={"username": f"unknown-{index}", "password": "invalid"},
                    headers={
                        "X-Forwarded-For": f"198.51.100.{index}",
                        "X-Real-IP": f"203.0.113.{index}",
                    },
                )
                for index in range(6)
            ]
        assert [response.status_code for response in responses] == [401, 401, 401, 401, 401, 429]
    finally:
        limiter.reset()
        limiter.enabled = original_enabled


async def test_login_rate_limit_keeps_different_peer_ips_separate() -> None:
    """One source exhausting its bucket does not throttle another source."""
    from app.api.routes.auth import limiter
    from app.main import app

    limiter.reset()
    original_enabled = limiter.enabled
    limiter.enabled = True
    try:
        first_transport = httpx.ASGITransport(app=app, client=("192.0.2.10", 12345))
        async with httpx.AsyncClient(
            transport=first_transport, base_url="http://testserver"
        ) as first_client:
            for index in range(5):
                response = await first_client.post(
                    "/auth/login", json={"username": f"first-{index}", "password": "invalid"}
                )
                assert response.status_code == 401

        second_transport = httpx.ASGITransport(app=app, client=("192.0.2.11", 12345))
        async with httpx.AsyncClient(
            transport=second_transport, base_url="http://testserver"
        ) as second_client:
            response = await second_client.post(
                "/auth/login",
                json={"username": "second-source", "password": "invalid"},
                headers={"X-Forwarded-For": "198.51.100.99"},
            )
        assert response.status_code == 401
    finally:
        limiter.reset()
        limiter.enabled = original_enabled
