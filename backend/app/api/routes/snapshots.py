from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy.orm import Session
from starlette.types import Receive, Scope, Send

from app.api.authorization import require_target_access
from app.api.deps import get_current_user, get_db, get_settings
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.models import Snapshot, User
from app.schemas import SnapshotRead

router = APIRouter(
    prefix="/snapshots",
    tags=["snapshots"],
    dependencies=[Depends(get_current_user)],
)

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


class WholeFileResponse(FileResponse):
    """Serve the whole artifact and ignore client Range headers.

    Starlette's multi-range merge loop is quadratic in the number of ranges, and
    the upgrade to 0.52.1 does not change that.  Screenshots are small PNGs that
    browsers load whole, so Range support buys nothing; HTTP lets a server ignore it.
    """

    def __init__(self, path: Path, media_type: str | None = None) -> None:
        super().__init__(path, media_type=media_type, headers={"accept-ranges": "none"})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        ignored = (b"range", b"if-range")
        headers = [(name, value) for name, value in scope["headers"] if name.lower() not in ignored]
        await super().__call__({**scope, "headers": headers}, receive, send)


def _resolve_contained_artifact(raw_path: str, data_dir: Path) -> Path:
    resolved_base = data_dir.resolve()
    resolved_file = Path(raw_path).resolve()
    if not resolved_file.is_relative_to(resolved_base) or not resolved_file.is_file():
        raise NotFoundError("Snapshot artifact not found")
    return resolved_file


def _normalised_screenshot_response(screenshot_path: Path, viewport_width: int) -> Response:
    """Serve legacy screenshots with the same viewport crop as new captures."""
    try:
        with Image.open(screenshot_path) as image:
            if image.width <= viewport_width:
                return WholeFileResponse(screenshot_path, media_type="image/png")
            output = BytesIO()
            image.crop((0, 0, viewport_width, image.height)).save(output, format="PNG")
    except OSError:
        # Let FileResponse preserve the normal error handling for a corrupt legacy artifact.
        return WholeFileResponse(screenshot_path, media_type="image/png")
    return Response(output.getvalue(), media_type="image/png")


@router.get("/{snapshot_id}", response_model=SnapshotRead)
async def get_snapshot(
    snapshot_id: str, db: DbSession, user: Annotated[User, Depends(get_current_user)]
) -> Snapshot:
    snapshot = db.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"Snapshot not found: {snapshot_id}")
    require_target_access(db, user, snapshot.target_id)
    return snapshot


@router.get("/{snapshot_id}/screenshot")
async def get_snapshot_screenshot(
    snapshot_id: str,
    db: DbSession,
    settings: AppSettings,
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    snapshot = db.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"Snapshot not found: {snapshot_id}")
    require_target_access(db, user, snapshot.target_id)

    screenshot_path = _resolve_contained_artifact(snapshot.screenshot_path, settings.data_dir_path)
    return _normalised_screenshot_response(screenshot_path, settings.VIEWPORT_WIDTH)


@router.get("/{snapshot_id}/screenshot/raw")
async def get_raw_snapshot_screenshot(
    snapshot_id: str,
    db: DbSession,
    settings: AppSettings,
    user: Annotated[User, Depends(get_current_user)],
) -> WholeFileResponse:
    snapshot = db.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"Snapshot not found: {snapshot_id}")
    require_target_access(db, user, snapshot.target_id)

    # Pre-normalisation snapshots only have screenshot_path; it is their raw evidence.
    raw_path = snapshot.raw_screenshot_path or snapshot.screenshot_path
    artifact_path = _resolve_contained_artifact(raw_path, settings.data_dir_path)
    return WholeFileResponse(artifact_path, media_type="image/png")


@router.get("/{snapshot_id}/text")
async def get_snapshot_text(
    snapshot_id: str,
    db: DbSession,
    settings: AppSettings,
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    snapshot = db.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"Snapshot not found: {snapshot_id}")
    require_target_access(db, user, snapshot.target_id)

    text_path = _resolve_contained_artifact(snapshot.text_path, settings.data_dir_path)
    return Response(text_path.read_text(encoding="utf-8"), media_type="text/plain; charset=utf-8")
