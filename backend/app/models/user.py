from datetime import datetime
from typing import Literal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'operator')", name="ck_users_role_fixed"),
        CheckConstraint(
            "registration_status IN ('pending', 'approved', 'rejected')",
            name="ck_users_registration_status",
        ),
        CheckConstraint(
            "registration_status = 'approved' OR is_active = 0",
            name="ck_users_pending_rejected_inactive",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[Literal["admin", "operator"]] = mapped_column(String, default="operator")
    display_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    registration_status: Mapped[str] = mapped_column(String(20), nullable=False, default="approved")
    registration_reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    registration_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    registration_rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Brute-force lockout state (naive UTC timestamps; see app.core.time.utcnow).
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    first_failed_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
