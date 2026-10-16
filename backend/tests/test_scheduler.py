from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.status import STATUS_AVAILABILITY_ISSUE, STATUS_CHECKING
from app.core.time import utcnow
from app.db.session import Base
from app.models import Snapshot, Target
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

    # First tick: persists the initial deadline with jitter.
    await scheduler._tick()
    with session_factory() as db:
        target = db.get(Target, target_id)
        assert target is not None and target.next_check_at is not None
        assert target.next_check_at > utcnow()

    # Expire the persisted deadline to simulate time elapsing.
    with session_factory() as db:
        target = db.get(Target, target_id)
        assert target is not None
        target.next_check_at = utcnow() - timedelta(seconds=1)
        db.commit()

    async def fake_capture(url, settings, out_dir):
        raise RuntimeError("expected test capture failure")

    # Second tick claims the due target and hands it to the attempt wrapper.
    with patch("app.services.scheduler.capture_snapshot", fake_capture):
        await scheduler._tick()
        assert scheduler.active_tasks_count >= 1
        with session_factory() as db:
            target = db.get(Target, target_id)
            assert target is not None and target.next_check_at is None
            assert target.check_run_id is not None

        # Drain on stop ensures no tasks or coroutines are abandoned (Opus 5 review 4.2)
        await scheduler.stop()
    assert scheduler.active_tasks_count == 0


@pytest.mark.asyncio
async def test_scheduler_skips_checking_target_without_claiming_it(tmp_path: Path):
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
    # A target currently marked Checking belongs to its active worker.
    await scheduler._tick()
    with session_factory() as db:
        target = db.get(Target, target_id)
        assert target is not None and target.next_check_at is None

    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_holds_new_url_candidate_after_failed_retry(tmp_path: Path):
    session_factory, _ = make_test_db(tmp_path)
    with session_factory() as db:
        target = Target(
            name="Pending Target",
            url="https://example.com/new",
            url_revision=2,
            status=STATUS_AVAILABILITY_ISSUE,
            is_active=True,
        )
        db.add(target)
        db.flush()
        db.add(Snapshot(
            target_id=target.id,
            url_revision=2,
            final_url=target.url,
            http_status=200,
            screenshot_path="candidate.png",
            text_path="candidate.txt",
            html_path="candidate.html",
            is_baseline=False,
        ))
        db.commit()
        target_id = target.id

    scheduler = CheckScheduler(Settings(DATA_DIR=str(tmp_path)), session_factory=session_factory)
    with session_factory() as db:
        target = db.get(Target, target_id)
        assert target is not None
        target.next_check_at = utcnow() - timedelta(seconds=1)
        db.commit()
    await scheduler._tick()
    assert scheduler.active_tasks_count == 0
    with session_factory() as db:
        target = db.get(Target, target_id)
        assert target is not None and target.next_check_at > utcnow()
    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_holds_first_revision_candidate_until_review(tmp_path: Path):
    session_factory, _ = make_test_db(tmp_path)
    with session_factory() as db:
        target = Target(name="First Candidate", url="https://example.com", is_active=True)
        db.add(target)
        db.flush()
        db.add(Snapshot(
            target_id=target.id,
            url_revision=1,
            final_url=target.url,
            http_status=200,
            screenshot_path="first.png",
            text_path="first.txt",
            html_path="first.html",
            is_baseline=False,
        ))
        db.commit()
        target_id = target.id

    scheduler = CheckScheduler(Settings(DATA_DIR=str(tmp_path)), session_factory=session_factory)
    with session_factory() as db:
        target = db.get(Target, target_id)
        assert target is not None
        target.next_check_at = utcnow() - timedelta(seconds=1)
        db.commit()
    await scheduler._tick()
    assert scheduler.active_tasks_count == 0
    with session_factory() as db:
        target = db.get(Target, target_id)
        assert target is not None and target.next_check_at > utcnow()
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
    # Tick purges targets that are no longer active
    await scheduler._tick()
    with session_factory() as db:
        target = db.get(Target, target_id)
        assert target is not None and target.next_check_at is None
    await scheduler.stop()
