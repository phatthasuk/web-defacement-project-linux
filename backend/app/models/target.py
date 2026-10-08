from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.status import STATUS_NEVER_CHECKED
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.tag import Tag


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    url_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String, nullable=False, default=STATUS_NEVER_CHECKED)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    # Hosts whose scripts/iframes/links are expected on this target (analytics,
    # tag managers, CDNs). Without it the structural detector would report the
    # site's own third parties on every check. Matching covers subdomains.
    allowed_domains: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list[Tag]] = relationship(
        secondary="target_tags", back_populates="targets", lazy="selectin", order_by="Tag.name"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
