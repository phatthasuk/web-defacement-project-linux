import time
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.status import STATUS_CHECKING
from app.db.session import Base
from app.models import Target
from app.services.scheduler import CheckScheduler


def make_test_db(tmp_path: Path) -> tuple[sessionmaker[Session], Path]:
    db_path = tmp_path / f"test-{uuid4()}.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine), db_path


@pytest.mark.asyncio
async def test_scheduler_start_and_stop(tmp_path: Path):
    session_factory, _ = make_test_db(tmp_path)
    settings = Settings(
        DATA_DIR=str(tmp_path),
        CHECK_INTERVAL_SECONDS=60,
        SCHEDULER_POLL_INTERVAL_SECONDS=1,
    )
    scheduler = CheckScheduler(settings, session_factory=session_factory)
    assert not scheduler.is_running

    await scheduler.start()
    assert scheduler.is_running

    await scheduler.stop()
    assert not scheduler.is_running


@pytest.mark.asyncio
async def test_scheduler_registers_and_triggers_due_target(tmp_path: Path):
    session_factory, _ = make_test_db(tmp_path)
    with session_factory() as db:
        target = Target(name="Test Target", url="https://example.com", is_active=True)
        db.add(target)
        db.commit()
        db.refresh(target)
        target_id = target.id

    settings = Settings(
        DATA_DIR=str(tmp_path),
        CHECK_INTERVAL_SECONDS=10,
        CHECK_JITTER_MAX_SECONDS=2,
        SCHEDULER_POLL_INTERVAL_SECONDS=1,
    )
    scheduler = CheckScheduler(settings, session_factory=session_factory)

    # First tick: registers target with initial jitter
    await scheduler._tick()
    assert target_id in scheduler._next_due_times
    assert scheduler._next_due_times[target_id] > time.time()

    # Manually expire the due time to simulate time elapsing
    scheduler._next_due_times[target_id] = time.time() - 1

    # Second tick: triggers the check, retains task reference, and reschedules next due time
    await scheduler._tick()
    assert scheduler.active_tasks_count >= 1
    assert scheduler._next_due_times[target_id] > time.time()

    # Drain on stop ensures no tasks or coroutines are abandoned (Opus 5 review 4.2)
    await scheduler.stop()
    assert scheduler.active_tasks_count == 0


@pytest.mark.asyncio
async def test_scheduler_retries_in_flight_target_in_60s(tmp_path: Path):
    """Review 6.3: Skipped check retries in 60s instead of waiting a full interval."""
    session_factory, _ = make_test_db(tmp_path)
    with session_factory() as db:
        target = Target(
            name="Checking Target",
            url="https://example.com",
            is_active=True,
            status=STATUS_CHECKING,
        )
        db.add(target)
        db.commit()
        db.refresh(target)
        target_id = target.id

    settings = Settings(
        DATA_DIR=str(tmp_path),
        CHECK_INTERVAL_SECONDS=3600,
    )
    scheduler = CheckScheduler(settings, session_factory=session_factory)
    scheduler._next_due_times[target_id] = time.time() - 10

    # Tick skips target because it is Checking, and schedules retry in 60s (not 3600s)
    now = time.time()
    await scheduler._tick()
    assert scheduler._next_due_times[target_id] < now + 120.0
    assert scheduler._next_due_times[target_id] >= now + 50.0

    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_purges_inactive_targets(tmp_path: Path):
    session_factory, _ = make_test_db(tmp_path)
    with session_factory() as db:
        target = Target(name="Inactive Target", url="https://example.com", is_active=False)
        db.add(target)
        db.commit()
        db.refresh(target)
        target_id = target.id

    settings = Settings(DATA_DIR=str(tmp_path))
    scheduler = CheckScheduler(settings, session_factory=session_factory)
    scheduler._next_due_times[target_id] = time.time() + 100

    # Tick purges targets that are no longer active
    await scheduler._tick()
    assert target_id not in scheduler._next_due_times
    await scheduler.stop()
