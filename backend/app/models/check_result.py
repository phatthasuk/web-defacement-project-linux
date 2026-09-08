import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CheckResult(Base):
    __tablename__ = "check_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    target_id: Mapped[str] = mapped_column(String(36), ForeignKey("targets.id"), nullable=False)
    baseline_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("snapshots.id"), nullable=False
    )
    current_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("snapshots.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    text_change_score: Mapped[float] = mapped_column(Float, nullable=False)
    visual_change_score: Mapped[float] = mapped_column(Float, nullable=False)
    # Structural detector (scripts, iframes, form actions, meta refresh, outbound
    # hosts). Defaults to 0.0 so rows written before this column existed read as
    # "no structural change" rather than failing.
    structure_change_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
