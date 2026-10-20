import asyncio
import logging
import random
import uuid
from contextlib import suppress
from datetime import timedelta

from sqlalchemy import select

from app.core.config import Settings
from app.core.status import STATUS_CHECKING
from app.core.time import utcnow
from app.db.session import SessionLocal
from app.models import Snapshot, Target
from app.services.attempts import run_check_attempt
from app.services.capture.capture import capture_snapshot
from app.services.check_progress import register_queued
from app.services.concurrency import (
    SessionFactory,
    release_in_flight,
    try_acquire_in_flight,
)

logger = logging.getLogger("app.scheduler")


class CheckScheduler:
    """In-process background scheduler for target checks.

    Stage 1.1: Runs checks automatically on a per-target interval with jitter to
    distribute network and browser load. Concurrency limits are automatically
    enforced by `run_checks_for_targets`.
    """

    def __init__(
        self,
        settings: Settings,
        session_factory: SessionFactory = SessionLocal,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self._stopping = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._background_tasks: set[asyncio.Task] = set()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def active_tasks_count(self) -> int:
        return len(self._background_tasks)

    async def start(self) -> None:
        if self.is_running:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run_loop(), name="check_scheduler_loop")
        logger.info(
            "CheckScheduler started: interval=%ds jitter=0-%ds poll=%ds",
            self.settings.CHECK_INTERVAL_SECONDS,
            self.settings.CHECK_JITTER_MAX_SECONDS,
            self.settings.SCHEDULER_POLL_INTERVAL_SECONDS,
        )

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        # Drain in-flight check tasks so shutdown does not abandon targets in Checking (F8 / Op 4.2)
        if self._background_tasks:
            logger.info(
                "Draining %d in-flight scheduled check tasks...", len(self._background_tasks)
            )
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()

        logger.info("CheckScheduler stopped")

    def _on_task_done(self, task: asyncio.Task) -> None:
        self._background_tasks.discard(task)
        if not task.cancelled():
            exc = task.exception()
            if exc:
                logger.exception("Scheduled check task failed with unhandled error: %s", exc)

    async def _run_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Unexpected error in CheckScheduler tick")

            try:
                await asyncio.wait_for(
                    self._stopping.wait(),
                    timeout=float(self.settings.SCHEDULER_POLL_INTERVAL_SECONDS),
                )
            except TimeoutError:
                pass

    async def _tick(self) -> None:
        now = utcnow()
        with self.session_factory() as db:
            active_target_ids = list(
                db.scalars(select(Target.id).where(Target.is_active.is_(True)))
            )
            candidate_exists = (
                select(Snapshot.id)
                .where(
                    Snapshot.target_id == Target.id,
                    Snapshot.url_revision == Target.url_revision,
                    Snapshot.is_baseline.is_(False),
                )
                .correlate(Target)
                .exists()
            )
            baseline_exists = (
                select(Snapshot.id)
                .where(
                    Snapshot.target_id == Target.id,
                    Snapshot.url_revision == Target.url_revision,
                    Snapshot.is_baseline.is_(True),
                )
                .correlate(Target)
                .exists()
            )
            pending_candidate_ids = set(
                db.scalars(select(Target.id).where(candidate_exists, ~baseline_exists))
            )

        for target_id in active_target_ids:
            with self.session_factory() as db:
                target = db.get(Target, target_id)
                if target is None or not target.is_active or target.status == STATUS_CHECKING:
                    continue

                if target.next_check_at is None:
                    if target.check_run_id is not None:
                        # An active manual run owns the target; its attempt wrapper
                        # will persist either the retry deadline or the hourly run.
                        continue
                    initial_delay = random.uniform(
                        1.0, min(float(self.settings.CHECK_JITTER_MAX_SECONDS), 60.0)
                    )
                    target.next_check_at = now + timedelta(seconds=initial_delay)
                    db.commit()
                    continue

                due_at = target.next_check_at
                if due_at.tzinfo is not None:
                    due_at = due_at.replace(tzinfo=None)
                if now < due_at:
                    continue

                if target_id in pending_candidate_ids and target.check_run_id is None:
                    # Wait for operator baseline approval without polling this
                    # candidate every minute or creating duplicate snapshots.
                    jitter = random.uniform(0.0, self.settings.CHECK_JITTER_MAX_SECONDS)
                    target.next_check_at = now + timedelta(
                        seconds=self.settings.CHECK_INTERVAL_SECONDS + jitter
                    )
                    db.commit()
                    continue

                if not try_acquire_in_flight(target_id):
                    continue

                try:
                    if target.check_run_id is None:
                        target.check_run_id = str(uuid.uuid4())
                        target.check_run_source = "scheduled"
                        target.check_attempt_count = 0
                    run_id = target.check_run_id
                    if run_id is None:
                        raise RuntimeError(f"Target {target.id} has no reserved check run")
                    target.next_check_at = None
                    target_id_for_log = target.id
                    target_name = target.name
                    url_revision = target.url_revision
                    db.commit()
                    register_queued(target_id_for_log, run_id, url_revision)

                    source = "scheduled"
                    logger.info(
                        "Scheduler triggering check for target %s (%s); attempt %d",
                        target_id_for_log,
                        target_name,
                        1,
                    )
                    task = asyncio.create_task(
                        run_check_attempt(
                            target_id_for_log,
                            self.settings,
                            run_id=run_id,
                            initial_source=source,
                            capture_func=capture_snapshot,
                            session_factory=self.session_factory,
                        ),
                        name=f"scheduled_check_{target_id_for_log}",
                    )
                    self._background_tasks.add(task)
                    task.add_done_callback(self._on_task_done)
                except Exception:
                    release_in_flight(target_id)
                    raise
