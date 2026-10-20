from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.authorization import accessible_targets
from app.core.config import Settings
from app.models import Target, User
from app.schemas.check_activity import ActiveCheckRead, CheckActivityRead, CheckProgressRead
from app.services.check_progress import get_progress


def list_active_checks(
    db: Session, user: User, settings: Settings, *, limit: int, offset: int
) -> CheckActivityRead:
    filters = (Target.is_active.is_(True), Target.check_run_id.is_not(None))
    count_query = accessible_targets(select(Target.id).where(*filters), user).order_by(None)
    total = db.scalar(select(func.count()).select_from(count_query.subquery())) or 0

    query = accessible_targets(
        select(
            Target.id,
            Target.name,
            Target.status,
            Target.url_revision,
            Target.check_run_id,
            Target.check_run_source,
            Target.check_attempt_count,
            Target.next_check_at,
            Target.last_error_code,
            Target.updated_at,
        ).where(*filters),
        user,
    ).order_by(Target.updated_at.asc(), Target.id.asc())
    rows = db.execute(query.limit(limit).offset(offset)).mappings().all()

    items: list[ActiveCheckRead] = []
    for row in rows:
        run_id = row["check_run_id"]
        progress_data = get_progress(row["id"], run_id, row["url_revision"])
        progress = CheckProgressRead.model_validate(progress_data) if progress_data else None
        items.append(
            ActiveCheckRead(
                id=row["id"],
                name=row["name"],
                status=row["status"],
                url_revision=row["url_revision"],
                check_run_id=run_id,
                check_run_source=row["check_run_source"],
                check_attempt_count=row["check_attempt_count"],
                check_retry_max_attempts=settings.CHECK_RETRY_MAX_ATTEMPTS,
                next_check_at=row["next_check_at"],
                last_error_code=row["last_error_code"],
                progress=progress,
            )
        )

    return CheckActivityRead(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        observed_at=datetime.now(UTC),
    )
