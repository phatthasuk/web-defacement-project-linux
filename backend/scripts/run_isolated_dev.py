#!/usr/bin/env python3
"""Run the backend against a disposable database for local UI checks.

The database and artifacts live outside backend/data (default: the system temp
directory, override with WDM_ISOLATED_DIR) and the scheduler is disabled, so
local runs never write live evidence or capture monitored sites on their own.
"Check Now" still performs a real capture; use only local fixture targets.

Examples, from backend/:
    python scripts/run_isolated_dev.py --create-user admin --role admin
    python scripts/run_isolated_dev.py
"""

import os
import runpy
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
LIVE_DATA_DIR = (BACKEND_DIR / "data").resolve()


def _isolated_dir() -> Path:
    raw = os.environ.get("WDM_ISOLATED_DIR") or str(
        Path(tempfile.gettempdir()) / "wdm-isolated-dev"
    )
    path = Path(raw).resolve()
    if path == LIVE_DATA_DIR or LIVE_DATA_DIR in path.parents:
        sys.exit(f"Refusing to use {path}: it is inside the live backend/data directory.")
    path.mkdir(parents=True, exist_ok=True)
    return path


def main() -> None:
    work_dir = _isolated_dir()
    # Process environment takes precedence over backend/.env in pydantic-settings.
    os.environ["DATABASE_URL"] = f"sqlite:///{(work_dir / 'app.db').as_posix()}"
    os.environ["DATA_DIR"] = str(work_dir / "data")
    os.environ["SCHEDULER_ENABLED"] = "false"
    os.environ["ENVIRONMENT"] = "development"
    os.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))
    print(f"Isolated backend data: {work_dir}", flush=True)

    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")

    if len(sys.argv) > 1 and sys.argv[1] == "--create-user":
        sys.argv = ["create_user.py", *sys.argv[2:]]
        runpy.run_path(str(BACKEND_DIR / "scripts" / "create_user.py"), run_name="__main__")
        return

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, workers=1)


if __name__ == "__main__":
    main()
