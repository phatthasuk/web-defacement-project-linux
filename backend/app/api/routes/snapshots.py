from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.errors import NotFoundError
from app.models import Snapshot
from app.schemas import SnapshotRead

router = APIRouter(
    prefix="/snapshots",
    tags=["snapshots"],
    dependencies=[Depends(get_current_user)],
)

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/{snapshot_id}", response_model=SnapshotRead)
async def get_snapshot(snapshot_id: str, db: DbSession) -> Snapshot:
    snapshot = db.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"Snapshot not found: {snapshot_id}")
    return snapshot


@router.get("/{snapshot_id}/screenshot")
async def get_snapshot_screenshot(snapshot_id: str, db: DbSession) -> FileResponse:
    snapshot = db.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"Snapshot not found: {snapshot_id}")

    screenshot_path = Path(snapshot.screenshot_path)
    if not screenshot_path.is_file():
        raise NotFoundError(f"Snapshot screenshot not found: {snapshot_id}")
    return FileResponse(screenshot_path, media_type="image/png")


@router.get("/{snapshot_id}/text")
async def get_snapshot_text(snapshot_id: str, db: DbSession) -> Response:
    snapshot = db.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"Snapshot not found: {snapshot_id}")

    text_path = Path(snapshot.text_path)
    if not text_path.is_file():
        raise NotFoundError(f"Snapshot text not found: {snapshot_id}")
    return Response(text_path.read_text(encoding="utf-8"), media_type="text/plain")
