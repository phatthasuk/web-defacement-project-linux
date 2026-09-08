import asyncio
import logging
import random
import time
from contextlib import suppress

from sqlalchemy import select

from app.core.config import Settings
from app.core.status import STATUS_CHECKING
from app.db.session import SessionLocal
from app.models import Target
from app.services.concurrency import SessionFactory, is_target_in_flight, run_checks_for_targets

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
        self._next_due_times: dict[str, float] = {}
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
        now = time.time()
        with self.session_factory() as db:
            active_targets = list(db.scalars(select(Target).where(Target.is_active.is_(True))))

        active_ids = {target.id for target in active_targets}

        # Purge tracking for removed or deactivated targets
        for target_id in list(self._next_due_times.keys()):
            if target_id not in active_ids:
                self._next_due_times.pop(target_id, None)

        for target in active_targets:
            if target.id not in self._next_due_times:
                # Stagger newly observed targets with an initial jitter delay
                initial_delay = random.uniform(
                    1.0, min(float(self.settings.CHECK_JITTER_MAX_SECONDS), 60.0)
                )
                self._next_due_times[target.id] = now + initial_delay
                logger.debug(
                    "Registered target %s with initial check due in %.1fs",
                    target.id,
                    initial_delay,
                )
                continue

            if now >= self._next_due_times[target.id]:
                # If target is already checking or in flight, retry in 60s rather than
                # advancing a full interval (Review 6.3)
                if target.status == STATUS_CHECKING or is_target_in_flight(target.id):
                    logger.debug(
                        "Skipping scheduled check for target %s: "
                        "check already in progress; retrying in 60s",
                        target.id,
                    )
                    self._next_due_times[target.id] = now + 60.0
                    continue

                # Schedule the subsequent check interval + jitter
                jitter = random.uniform(0.0, float(self.settings.CHECK_JITTER_MAX_SECONDS))
                self._next_due_times[target.id] = (
                    now + float(self.settings.CHECK_INTERVAL_SECONDS) + jitter
                )

                logger.info(
                    "Scheduler triggering check for target %s (%s); next check in %.1fs",
                    target.id,
                    target.name,
                    float(self.settings.CHECK_INTERVAL_SECONDS) + jitter,
                )
                task = asyncio.create_task(
                    run_checks_for_targets(
                        [target.id],
                        self.settings,
                        session_factory=self.session_factory,
                    ),
                    name=f"scheduled_check_{target.id}",
                )
                self._background_tasks.add(task)
                task.add_done_callback(self._on_task_done)
