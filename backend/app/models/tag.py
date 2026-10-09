from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.target import Target


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        Index(
            "uq_tags_root_normalized_name",
            "normalized_name",
            unique=True,
            sqlite_where=text("parent_id IS NULL"),
            postgresql_where=text("parent_id IS NULL"),
        ),
        Index(
            "uq_tags_child_normalized_name",
            "parent_id",
            "normalized_name",
            unique=True,
            sqlite_where=text("parent_id IS NOT NULL"),
            postgresql_where=text("parent_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(50), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tags.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    color_key: Mapped[str] = mapped_column(String(20), nullable=False, default="cyan")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    targets: Mapped[list[Target]] = relationship(
        secondary="target_tags", back_populates="tags", lazy="selectin"
    )
    parent: Mapped[Tag | None] = relationship(
        remote_side=lambda: [Tag.id], back_populates="children", lazy="joined"
    )
    children: Mapped[list[Tag]] = relationship(
        back_populates="parent", cascade="save-update, merge", order_by="Tag.name"
    )

    @property
    def parent_name(self) -> str | None:
        return self.parent.name if self.parent is not None else None
