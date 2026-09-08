"""Create a local user account.

The password is read interactively (or from stdin for automation) so it never
appears in shell history, process listings, or CI logs. Every failure path
returns a non-zero exit code.
"""

import argparse
import getpass
import sys

from app.core.security import get_password_hash
from app.db.session import Base, SessionLocal, engine
from app.models.user import User

MIN_PASSWORD_LENGTH = 12


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

    return password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local user account.")
    parser.add_argument("username", help="Username for the new account")
    parser.add_argument(
        "--role",
        default="authenticated-user",
        help="Role to assign (default: authenticated-user)",
    )
    args = parser.parse_args()

    username = args.username.strip()
    if not username:
        print("Username must not be empty.", file=sys.stderr)
        sys.exit(1)

    password = _read_password()

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == username).first() is not None:
            print(f"User {username!r} already exists.", file=sys.stderr)
            sys.exit(1)

        db.add(
            User(
                username=username,
                hashed_password=get_password_hash(password),
                is_active=True,
                role=args.role,
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
