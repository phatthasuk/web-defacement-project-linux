"""Create a local user account.

The password is read interactively (or from stdin for automation) so it never
appears in shell history, process listings, or CI logs. Every failure path
returns a non-zero exit code.
"""

import argparse
import getpass
import sys
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.security import get_password_hash
from app.core.time import utcnow
from app.db.session import SessionLocal
from app.models.member import MemberAuditEvent
from app.models.session import Session
from app.models.user import User

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 200


def _read_password() -> str:
    if not sys.stdin.isatty():
        # Automation: read a single line from stdin (e.g. deployment secret).
        password = sys.stdin.readline().rstrip("\n")
        confirm = password
    else:
        password = getpass.getpass(prompt="Password: ")
        confirm = getpass.getpass(prompt="Confirm password: ")

    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        sys.exit(1)

    if len(password) < MIN_PASSWORD_LENGTH:
        print(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(password) > MAX_PASSWORD_LENGTH:
        print(
            f"Password must be no longer than {MAX_PASSWORD_LENGTH} characters.",
            file=sys.stderr,
        )
        sys.exit(1)

    return password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local user account.")
    parser.add_argument("username", help="Username for the new account")
    parser.add_argument(
        "--role",
        choices=("admin", "operator"),
        default="operator",
        help="Fixed role for a new account (default: operator)",
    )
    parser.add_argument("--display-name", help="Display name (defaults to username)")
    parser.add_argument(
        "--reset-existing",
        action="store_true",
        help="Controlled password recovery for an existing account",
    )
    args = parser.parse_args()

    username = args.username.strip()
    if not username:
        print("Username must not be empty.", file=sys.stderr)
        sys.exit(1)

    password = _read_password()

    db = SessionLocal()
    try:
        from sqlalchemy import text

        from alembic.config import Config
        from alembic.script import ScriptDirectory

        alembic_config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
        head = ScriptDirectory.from_config(alembic_config).get_current_head()
        current = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        if current != head:
            raise RuntimeError(
                f"Database must be migrated to {head} before account setup (current: {current})"
            )

        existing = db.query(User).filter(User.username == username).first()
        now = utcnow()
        if existing is not None:
            if not args.reset_existing:
                print(f"User {username!r} already exists.", file=sys.stderr)
                sys.exit(1)
            existing.hashed_password = get_password_hash(password)
            existing.failed_login_count = 0
            existing.first_failed_login_at = None
            existing.locked_until = None
            existing.password_changed_at = now
            existing.must_change_password = existing.role == "operator"
            db.query(Session).filter(
                Session.user_id == existing.id, Session.revoked_at.is_(None)
            ).update(
                {
                    Session.revoked_at: now,
                    Session.revocation_reason: "controlled_password_recovery",
                },
                synchronize_session=False,
            )
            db.add(
                MemberAuditEvent(
                    actor_id=None,
                    member_id=existing.id,
                    action="member.password_recovered",
                    source="controlled_setup",
                    occurred_at=now,
                    after={"must_change_password": existing.must_change_password},
                )
            )
            db.commit()
            print(f"Password recovered for {username!r}; all existing sessions were revoked.")
            return

        user = User(
            username=username,
            display_name=(args.display_name or username).strip(),
            hashed_password=get_password_hash(password),
            is_active=True,
            role=args.role,
            registration_status="approved",
            must_change_password=args.role == "operator",
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
        db.add(
            MemberAuditEvent(
                actor_id=None,
                member_id=user.id,
                action="member.created",
                source="controlled_setup",
                occurred_at=now,
                after={"role": args.role, "registration_status": "approved", "is_active": True},
            )
        )
        db.commit()
        print(f"User {username!r} created successfully.")
    except Exception as exc:  # noqa: BLE001 - surface any failure as non-zero exit
        db.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
