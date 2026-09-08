import asyncio
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.status import (
    STATUS_AVAILABILITY_ISSUE,
    STATUS_CHECKING,
    STATUS_FAILED,
    STATUS_OK,
)
from app.db.session import Base
from app.models import Snapshot, Target
from app.services.capture.capture import CaptureResult
from app.services.concurrency import RESULT_SKIPPED, run_checks_for_targets


def make_session_factory(prefix: str, tmp_path: Path) -> tuple[Callable[[], Session], Path]:
    work_dir = tmp_path / f"{prefix}-{uuid4()}"
    work_dir.mkdir(parents=True, exist_ok=True)
    db_path = work_dir / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine), work_dir


async def test_run_checks_for_targets_respects_global_cap(tmp_path: Path):
    session_factory, work_dir = make_session_factory("concurrency-global", tmp_path)
    target_ids = create_targets(
        session_factory,
        [f"https://site-{index}.example.com" for index in range(5)],
    )
    counter = ActiveCounter()

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        active = await counter.increment()
        counter.max_active = max(counter.max_active, active)
        await asyncio.sleep(0.05)
        await counter.decrement()
        return write_capture(out_dir, f"global-{uuid4()}", url, "white")

    results = await run_checks_for_targets(
        target_ids,
        Settings(
            DATA_DIR=str(work_dir),
            MAX_CONCURRENT_CHECKS=2,
            PER_DOMAIN_CONCURRENCY=1,
        ),
        capture_func=fake_capture,
        session_factory=session_factory,
    )

    assert counter.max_active <= 2
    assert [result.status for result in results] == [STATUS_OK] * 5


async def test_run_checks_for_targets_respects_per_domain_cap(tmp_path: Path):
    session_factory, work_dir = make_session_factory("concurrency-domain", tmp_path)
    target_ids = create_targets(
        session_factory,
        [
            "https://same.example.com/a",
            "https://same.example.com/b",
            "https://same.example.com/c",
            "https://other.example.com/a",
        ],
    )
    counter = ActiveCounter()
    active_by_host: dict[str, int] = defaultdict(int)
    max_by_host: dict[str, int] = defaultdict(int)

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        host = urlparse(url).hostname or url
        async with counter.lock:
            active_by_host[host] += 1
            max_by_host[host] = max(max_by_host[host], active_by_host[host])
        await asyncio.sleep(0.05)
        async with counter.lock:
            active_by_host[host] -= 1
        return write_capture(out_dir, f"domain-{uuid4()}", url, "white")

    results = await run_checks_for_targets(
        target_ids,
        Settings(
            DATA_DIR=str(work_dir),
            MAX_CONCURRENT_CHECKS=3,
            PER_DOMAIN_CONCURRENCY=1,
        ),
        capture_func=fake_capture,
        session_factory=session_factory,
    )

    assert max_by_host["same.example.com"] <= 1
    assert [result.status for result in results] == [STATUS_OK] * 4


async def test_run_checks_for_targets_skips_already_checking_target(tmp_path: Path):
    session_factory, work_dir = make_session_factory("concurrency-skip", tmp_path)
    target_ids = create_targets(
        session_factory,
        ["https://checking.example.com", "https://ready.example.com"],
    )
    with session_factory() as db:
        checking_target = db.get(Target, target_ids[0])
        assert checking_target is not None
        checking_target.status = STATUS_CHECKING
        db.commit()

    called_urls: list[str] = []

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        called_urls.append(url)
        return write_capture(out_dir, f"skip-{uuid4()}", url, "white")

    results = await run_checks_for_targets(
        target_ids,
        Settings(DATA_DIR=str(work_dir)),
        capture_func=fake_capture,
        session_factory=session_factory,
    )

    assert results[0].status == RESULT_SKIPPED
    assert results[0].skipped is True
    assert called_urls == ["https://ready.example.com"]


async def test_run_checks_for_targets_marks_timeout_failed(tmp_path: Path):
    session_factory, work_dir = make_session_factory("concurrency-timeout", tmp_path)
    target_ids = create_targets(session_factory, ["https://slow.example.com"])

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        await asyncio.sleep(1)
        return write_capture(out_dir, f"timeout-{uuid4()}", url, "white")

    results = await run_checks_for_targets(
        target_ids,
        Settings(DATA_DIR=str(work_dir)),
        capture_func=fake_capture,
        session_factory=session_factory,
        timeout_seconds=0.05,
    )

    with session_factory() as db:
        target = db.get(Target, target_ids[0])
        assert target is not None
        assert target.status == STATUS_AVAILABILITY_ISSUE
        assert list(db.scalars(select(Snapshot))) == []

    assert results[0].status == STATUS_AVAILABILITY_ISSUE
    assert results[0].error is not None


async def test_run_checks_for_targets_isolates_expected_capture_failures(tmp_path: Path):
    session_factory, work_dir = make_session_factory("concurrency-isolation", tmp_path)
    target_ids = create_targets(
        session_factory,
        ["https://fail.example.com", "https://ok.example.com"],
    )

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        if "fail" in url:
            raise RuntimeError("capture failed")
        return write_capture(out_dir, f"isolation-{uuid4()}", url, "white")

    results = await run_checks_for_targets(
        target_ids,
        Settings(DATA_DIR=str(work_dir)),
        capture_func=fake_capture,
        session_factory=session_factory,
    )

    assert results[0].status == STATUS_FAILED
    assert results[1].status == STATUS_OK

    with session_factory() as db:
        t1 = db.get(Target, target_ids[0])
        t2 = db.get(Target, target_ids[1])
        assert t1 is not None
        assert t2 is not None
        assert t1.status == STATUS_FAILED
        assert t1.last_error == "capture failed"
        assert t2.status == STATUS_OK
        assert t2.last_error is None



async def test_run_checks_for_targets_commits_worker_sessions(tmp_path: Path):
    session_factory, work_dir = make_session_factory("concurrency-commits", tmp_path)
    target_ids = create_targets(
        session_factory,
        ["https://one.example.com", "https://two.example.com"],
    )

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        return write_capture(out_dir, f"commit-{uuid4()}", url, "white")

    await run_checks_for_targets(
        target_ids,
        Settings(DATA_DIR=str(work_dir), MAX_CONCURRENT_CHECKS=2),
        capture_func=fake_capture,
        session_factory=session_factory,
    )

    with session_factory() as db:
        targets = list(db.scalars(select(Target).order_by(Target.url)))
        snapshots = list(db.scalars(select(Snapshot)))

    assert [target.status for target in targets] == [STATUS_OK, STATUS_OK]
    assert len(snapshots) == 2


def create_targets(session_factory: Callable[[], Session], urls: list[str]) -> list[str]:
    with session_factory() as db:
        targets = [
            Target(name=f"Target {index}", url=url)
            for index, url in enumerate(urls, start=1)
        ]
        db.add_all(targets)
        db.commit()
        for target in targets:
            db.refresh(target)
        return [target.id for target in targets]


def write_capture(out_dir: Path, snapshot_id: str, text: str, color: str) -> CaptureResult:
    screenshot_path = out_dir / "screenshots" / f"{snapshot_id}.png"
    text_path = out_dir / "text" / f"{snapshot_id}.txt"
    html_path = out_dir / "html" / f"{snapshot_id}.html"

    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)

    Image.new("RGB", (2, 2), color).save(screenshot_path)
    text_path.write_text(text, encoding="utf-8")
    html_path.write_text(f"<html><body>{text}</body></html>", encoding="utf-8")

    return CaptureResult(
        id=snapshot_id,
        url=text,
        final_url=text,
        http_status=200,
        title="Example",
        screenshot_path=str(screenshot_path),
        text_path=str(text_path),
        html_path=str(html_path),
        redirect_count=0,
    )


class ActiveCounter:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.lock = asyncio.Lock()

    async def increment(self) -> int:
        async with self.lock:
            self.active += 1
            return self.active

    async def decrement(self) -> None:
        async with self.lock:
            self.active -= 1
