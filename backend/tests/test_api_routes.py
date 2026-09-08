import asyncio
from pathlib import Path
from uuid import uuid4

import httpx
from PIL import Image
from sqlalchemy.orm import Session

from app.api.deps import get_capture_func
from app.core.status import (
    STATUS_ACKNOWLEDGED,
    STATUS_CHANGED,
    STATUS_CHECKING,
    STATUS_DEFACED,
    STATUS_OK,
)
from app.main import app
from app.models import Snapshot, Target
from app.services.capture.capture import CaptureResult


async def test_targets_crud_and_soft_delete(
    client: httpx.AsyncClient,
    api_capture_calls: list[str],
):
    create_response = await client.post(
        "/targets",
        json={"name": "Example", "url": "https://93.184.216.34"},
    )
    assert create_response.status_code == 201
    target = create_response.json()
    target_id = target["id"]
    assert target["is_active"] is True

    ssrf_response = await client.post(
        "/targets",
        json={"name": "Localhost", "url": "http://127.0.0.1"},
    )
    assert ssrf_response.status_code == 400

    list_response = await client.get("/targets")
    assert [item["id"] for item in list_response.json()] == [target_id]

    get_response = await client.get(f"/targets/{target_id}")
    assert get_response.status_code == 200

    missing_response = await client.get(f"/targets/{uuid4()}")
    assert missing_response.status_code == 404

    patch_response = await client.patch(f"/targets/{target_id}", json={"name": "Renamed"})
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Renamed"

    valid_url_patch = await client.patch(
        f"/targets/{target_id}",
        json={"name": "Renamed Site", "url": "https://93.184.216.35"},
    )
    assert valid_url_patch.status_code == 200
    assert valid_url_patch.json()["name"] == "Renamed Site"
    assert valid_url_patch.json()["url"] == "https://93.184.216.35"

    ssrf_patch = await client.patch(
        f"/targets/{target_id}",
        json={"url": "http://127.0.0.1"},
    )
    assert ssrf_patch.status_code == 400

    delete_response = await client.delete(f"/targets/{target_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["is_active"] is False

    assert (await client.get("/targets")).json() == []
    inactive_response = await client.get("/targets?include_inactive=true")
    assert [item["id"] for item in inactive_response.json()] == [target_id]
    assert api_capture_calls == []


async def test_check_trigger_runs_background_check(
    client: httpx.AsyncClient,
    api_capture_calls: list[str],
):
    target_id = await create_target(client)

    response = await client.post(f"/targets/{target_id}/check")

    assert response.status_code == 202
    assert response.json() == {"target_id": target_id, "accepted": True}
    target_response = await client.get(f"/targets/{target_id}")
    assert target_response.json()["status"] == STATUS_OK
    assert api_capture_calls == ["https://93.184.216.34"]


async def test_check_trigger_missing_target_does_not_schedule_background_task(
    client: httpx.AsyncClient,
    api_capture_calls: list[str],
):
    response = await client.post(f"/targets/{uuid4()}/check")

    assert response.status_code == 404
    assert api_capture_calls == []


async def test_double_check_trigger_skips_in_flight_duplicate(
    client: httpx.AsyncClient,
    api_capture_calls: list[str],
):
    target_id = await create_target(client)

    async def slow_capture(url: str, settings, out_dir: Path) -> CaptureResult:
        api_capture_calls.append(url)
        await asyncio.sleep(0.1)
        return write_capture(out_dir, f"slow-{uuid4()}", url, "white")

    app.dependency_overrides[get_capture_func] = lambda: slow_capture

    first_response, second_response = await asyncio.gather(
        client.post(f"/targets/{target_id}/check"),
        client.post(f"/targets/{target_id}/check"),
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert api_capture_calls == ["https://93.184.216.34"]


async def test_checks_and_snapshots_read_paths(
    client: httpx.AsyncClient,
    api_session_factory,
    api_work_dir: Path,
):
    target_id = await create_target(client)

    empty_checks = await client.get(f"/targets/{target_id}/checks")
    assert empty_checks.status_code == 200
    assert empty_checks.json() == []

    missing_target_checks = await client.get(f"/targets/{uuid4()}/checks")
    assert missing_target_checks.status_code == 404

    snapshot_id = "snapshot-api"
    with api_session_factory() as db:
        snapshot = Snapshot(
            id=snapshot_id,
            target_id=target_id,
            final_url="https://93.184.216.34",
            http_status=200,
            title="Example",
            screenshot_path=str(api_work_dir / "screenshots" / f"{snapshot_id}.png"),
            text_path=str(api_work_dir / "text" / f"{snapshot_id}.txt"),
            html_path=str(api_work_dir / "html" / f"{snapshot_id}.html"),
            is_baseline=True,
        )
        capture = write_capture(api_work_dir, snapshot_id, "hello", "white")
        snapshot.screenshot_path = capture.screenshot_path
        snapshot.text_path = capture.text_path
        snapshot.html_path = capture.html_path
        db.add(snapshot)
        db.commit()

    snapshot_response = await client.get(f"/snapshots/{snapshot_id}")
    assert snapshot_response.status_code == 200
    assert "screenshot_path" not in snapshot_response.json()

    screenshot_response = await client.get(f"/snapshots/{snapshot_id}/screenshot")
    assert screenshot_response.status_code == 200
    assert screenshot_response.headers["content-type"] == "image/png"

    text_response = await client.get(f"/snapshots/{snapshot_id}/text")
    assert text_response.status_code == 200
    assert text_response.text == "hello"

    Path(capture.text_path).unlink()
    missing_file_response = await client.get(f"/snapshots/{snapshot_id}/text")
    assert missing_file_response.status_code == 404

    assert (await client.get(f"/checks/{uuid4()}")).status_code == 404
    assert (await client.get(f"/snapshots/{uuid4()}")).status_code == 404


async def test_review_flow_end_to_end(
    client: httpx.AsyncClient,
    api_capture_calls: list[str],
):
    target_id = await create_target(client)
    captures = [
        ("baseline", "Hello", "white"),
        ("current", "Changed", "black"),
    ]

    async def queued_capture(url: str, settings, out_dir: Path) -> CaptureResult:
        api_capture_calls.append(url)
        snapshot_id, text, color = captures.pop(0)
        return write_capture(out_dir, snapshot_id, text, color)

    app.dependency_overrides[get_capture_func] = lambda: queued_capture

    await client.post(f"/targets/{target_id}/check")
    await client.post(f"/targets/{target_id}/check")

    target_response = await client.get(f"/targets/{target_id}")
    assert target_response.json()["status"] == STATUS_CHANGED

    checks_response = await client.get(f"/targets/{target_id}/checks")
    checks = checks_response.json()
    assert len(checks) == 1
    check_id = checks[0]["id"]
    current_snapshot_id = checks[0]["current_snapshot_id"]
    assert checks[0]["acknowledged_at"] is None

    ack_response = await client.post(f"/checks/{check_id}/ack")
    assert ack_response.status_code == 200
    assert ack_response.json()["acknowledged_at"] is not None
    assert (await client.get(f"/targets/{target_id}")).json()["status"] == STATUS_ACKNOWLEDGED

    approve_response = await client.post(
        f"/targets/{target_id}/baseline/approve",
        json={"snapshot_id": current_snapshot_id},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["is_baseline"] is True
    assert (await client.get(f"/targets/{target_id}")).json()["status"] == STATUS_OK


async def test_confirm_defaced_route_updates_status(
    client: httpx.AsyncClient,
    api_capture_calls: list[str],
):
    target_id = await create_target(client)
    captures = [
        ("baseline", "Hello", "white"),
        ("current", "Changed", "black"),
    ]

    async def queued_capture(url: str, settings, out_dir: Path) -> CaptureResult:
        api_capture_calls.append(url)
        snapshot_id, text, color = captures.pop(0)
        return write_capture(out_dir, snapshot_id, text, color)

    app.dependency_overrides[get_capture_func] = lambda: queued_capture

    await client.post(f"/targets/{target_id}/check")
    await client.post(f"/targets/{target_id}/check")

    checks = (await client.get(f"/targets/{target_id}/checks")).json()
    check_id = checks[0]["id"]

    confirm_res = await client.post(f"/checks/{check_id}/confirm-defaced")
    assert confirm_res.status_code == 200
    assert confirm_res.json()["acknowledged_at"] is not None

    target = (await client.get(f"/targets/{target_id}")).json()
    assert target["status"] == STATUS_DEFACED


async def test_error_mapping_returns_expected_status_codes(
    client: httpx.AsyncClient,
    api_session_factory,
):
    not_found_response = await client.get(f"/targets/{uuid4()}")
    assert not_found_response.status_code == 404

    target_id = await create_target(client)
    with api_session_factory() as db:
        target = db.get(Target, target_id)
        assert target is not None
        snapshot = Snapshot(
            id="foreign-snapshot",
            target_id=create_target_row(db, "Other").id,
            final_url="https://93.184.216.34",
            http_status=200,
            title="Example",
            screenshot_path="missing.png",
            text_path="missing.txt",
            html_path="missing.html",
            is_baseline=False,
        )
        db.add(snapshot)
        db.commit()

    validation_response = await client.post(
        f"/targets/{target_id}/baseline/approve",
        json={"snapshot_id": "foreign-snapshot"},
    )
    assert validation_response.status_code == 400

    with api_session_factory() as db:
        target_2 = create_target_row(db, "Target 2")
        snapshot_2 = Snapshot(
            id="never-checked-snapshot",
            target_id=target_2.id,
            final_url="https://93.184.216.34",
            http_status=200,
            title="Example",
            screenshot_path="missing.png",
            text_path="missing.txt",
            html_path="missing.html",
            is_baseline=False,
        )
        db.add(snapshot_2)
        db.commit()
        target_2_id = target_2.id

    conflict_response = await client.post(
        f"/targets/{target_2_id}/baseline/approve",
        json={"snapshot_id": "never-checked-snapshot"},
    )
    assert conflict_response.status_code == 409



async def create_target(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/targets",
        json={"name": f"Target {uuid4()}", "url": "https://93.184.216.34"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_target_row(db: Session, name: str) -> Target:
    target = Target(name=name, url="https://93.184.216.34")
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


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


async def test_list_target_snapshots(
    client: httpx.AsyncClient,
    api_session_factory,
):
    from datetime import UTC, datetime, timedelta

    # 1. 404 for unknown target
    missing_response = await client.get(f"/targets/{uuid4()}/snapshots")
    assert missing_response.status_code == 404

    # 2. 200 + [] for target with no snapshots
    target_id = await create_target(client)
    empty_response = await client.get(f"/targets/{target_id}/snapshots")
    assert empty_response.status_code == 200
    assert empty_response.json() == []

    # 3. 200 + list of snapshots, ordered newest-first
    with api_session_factory() as db:
        s1 = Snapshot(
            id="snap-1",
            target_id=target_id,
            final_url="https://93.184.216.34",
            http_status=200,
            title="Example 1",
            screenshot_path="missing1.png",
            text_path="missing1.txt",
            html_path="missing1.html",
            is_baseline=True,
            captured_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        s2 = Snapshot(
            id="snap-2",
            target_id=target_id,
            final_url="https://93.184.216.34",
            http_status=200,
            title="Example 2",
            screenshot_path="missing2.png",
            text_path="missing2.txt",
            html_path="missing2.html",
            is_baseline=False,
            captured_at=datetime.now(UTC),
        )
        db.add(s1)
        db.add(s2)
        db.commit()

    list_response = await client.get(f"/targets/{target_id}/snapshots")
    assert list_response.status_code == 200
    data = list_response.json()
    assert len(data) == 2
    assert data[0]["id"] == "snap-2"
    assert data[1]["id"] == "snap-1"
    assert data[1]["is_baseline"] is True
    assert data[0]["is_baseline"] is False


async def test_trigger_check_inactive_target_returns_400(
    client: httpx.AsyncClient,
    api_capture_calls: list[str],
):
    target_id = await create_target(client)
    delete_response = await client.delete(f"/targets/{target_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["is_active"] is False

    response = await client.post(f"/targets/{target_id}/check")
    assert response.status_code == 400
    assert "inactive" in response.json()["detail"].lower()
    assert api_capture_calls == []


async def test_trigger_check_when_already_checking_returns_accepted_false(
    client: httpx.AsyncClient,
    api_session_factory,
):
    target_id = await create_target(client)
    with api_session_factory() as db:
        target = db.get(Target, target_id)
        assert target is not None
        target.status = "Checking"
        db.commit()

    response = await client.post(f"/targets/{target_id}/check")
    assert response.status_code == 202
    assert response.json()["accepted"] is False


async def test_get_config_returns_thresholds(client: httpx.AsyncClient):
    response = await client.get("/config")
    assert response.status_code == 200
    data = response.json()
    assert "text_change_threshold" in data
    assert "visual_change_threshold" in data
    assert isinstance(data["text_change_threshold"], float)
    assert isinstance(data["visual_change_threshold"], float)


async def test_list_and_demote_target_baselines(
    client: httpx.AsyncClient,
    api_session_factory,
):
    target_id = await create_target(client)
    with api_session_factory() as db:
        s1 = Snapshot(
            id="s-baseline-1",
            target_id=target_id,
            final_url="https://93.184.216.34",
            http_status=200,
            title="Example 1",
            screenshot_path="missing1.png",
            text_path="missing1.txt",
            html_path="missing1.html",
            is_baseline=True,
        )
        s2 = Snapshot(
            id="s-baseline-2",
            target_id=target_id,
            final_url="https://93.184.216.34",
            http_status=200,
            title="Example 2",
            screenshot_path="missing2.png",
            text_path="missing2.txt",
            html_path="missing2.html",
            is_baseline=True,
        )
        s3 = Snapshot(
            id="s-not-baseline",
            target_id=target_id,
            final_url="https://93.184.216.34",
            http_status=200,
            title="Example 3",
            screenshot_path="missing3.png",
            text_path="missing3.txt",
            html_path="missing3.html",
            is_baseline=False,
        )
        db.add_all([s1, s2, s3])
        db.commit()

    # List baselines: should return s1 and s2 only
    res = await client.get(f"/targets/{target_id}/baselines")
    assert res.status_code == 200
    baselines = res.json()
    assert len(baselines) == 2
    ids = [b["id"] for b in baselines]
    assert "s-baseline-1" in ids
    assert "s-baseline-2" in ids
    assert "s-not-baseline" not in ids

    # Demote s1
    demote_res = await client.post(f"/targets/{target_id}/baselines/s-baseline-1/demote")
    assert demote_res.status_code == 200
    assert demote_res.json()["is_baseline"] is False

    # List again: should only have s2
    res2 = await client.get(f"/targets/{target_id}/baselines")
    assert res2.status_code == 200
    assert len(res2.json()) == 1
    assert res2.json()[0]["id"] == "s-baseline-2"

    # Demoting already demoted snapshot should return 400
    demote_fail = await client.post(f"/targets/{target_id}/baselines/s-baseline-1/demote")
    assert demote_fail.status_code == 400

    # Demoting non-existent snapshot should return 404
    demote_404 = await client.post(f"/targets/{target_id}/baselines/non-existent/demote")
    assert demote_404.status_code == 404






async def test_demote_refuses_to_remove_the_only_baseline(
    client: httpx.AsyncClient,
    api_session_factory,
):
    """Removing the last baseline would let the next check adopt the live page.

    With no baseline left, run_target_check takes its `baseline is None` path and
    marks whatever it captures as the new baseline, reporting OK without a
    CheckResult. If the site were defaced at that moment the defacement would
    silently become the reference.
    """
    target_id = await create_target(client)
    with api_session_factory() as db:
        db.add(
            Snapshot(
                id="s-only-baseline",
                target_id=target_id,
                final_url="https://93.184.216.34",
                http_status=200,
                title="Only baseline",
                screenshot_path="only.png",
                text_path="only.txt",
                html_path="only.html",
                is_baseline=True,
            )
        )
        db.commit()

    res = await client.post(f"/targets/{target_id}/baselines/s-only-baseline/demote")

    assert res.status_code == 400
    assert "only baseline" in res.json()["detail"].lower()

    # The baseline must still be active.
    listed = await client.get(f"/targets/{target_id}/baselines")
    assert [b["id"] for b in listed.json()] == ["s-only-baseline"]


async def test_demote_allowed_once_a_replacement_baseline_exists(
    client: httpx.AsyncClient,
    api_session_factory,
):
    """The documented way to replace a sole baseline: approve first, then demote."""
    target_id = await create_target(client)
    with api_session_factory() as db:
        db.add_all(
            [
                Snapshot(
                    id="s-old",
                    target_id=target_id,
                    final_url="https://93.184.216.34",
                    http_status=200,
                    title="Old",
                    screenshot_path="old.png",
                    text_path="old.txt",
                    html_path="old.html",
                    is_baseline=True,
                ),
                Snapshot(
                    id="s-new",
                    target_id=target_id,
                    final_url="https://93.184.216.34",
                    http_status=200,
                    title="New",
                    screenshot_path="new.png",
                    text_path="new.txt",
                    html_path="new.html",
                    is_baseline=True,
                ),
            ]
        )
        db.commit()

    res = await client.post(f"/targets/{target_id}/baselines/s-old/demote")
    assert res.status_code == 200

    listed = await client.get(f"/targets/{target_id}/baselines")
    assert [b["id"] for b in listed.json()] == ["s-new"]

    # And the replacement is now itself protected.
    res2 = await client.post(f"/targets/{target_id}/baselines/s-new/demote")
    assert res2.status_code == 400


async def test_update_target_guards_url_change_during_check(
    client: httpx.AsyncClient,
    api_session_factory,
):
    target_id = await create_target(client)

    # 1. Update name while idle: OK
    res = await client.patch(f"/targets/{target_id}", json={"name": "New Name"})
    assert res.status_code == 200
    assert res.json()["name"] == "New Name"

    # 2. Update URL while idle: OK
    res = await client.patch(f"/targets/{target_id}", json={"url": "https://93.184.216.34/updated"})
    assert res.status_code == 200
    assert res.json()["url"] == "https://93.184.216.34/updated"

    # Set status to Checking
    with api_session_factory() as db:
        target = db.get(Target, target_id)
        assert target is not None
        target.status = STATUS_CHECKING
        db.commit()

    # 3. Submitting the same URL while Checking: OK (does not trigger conflict)
    res_same = await client.patch(
        f"/targets/{target_id}",
        json={"url": "https://93.184.216.34/updated", "name": "Checking Name"},
    )
    assert res_same.status_code == 200
    assert res_same.json()["name"] == "Checking Name"

    # 4. Updating name only while Checking: OK
    res_name = await client.patch(f"/targets/{target_id}", json={"name": "Another Name"})
    assert res_name.status_code == 200
    assert res_name.json()["name"] == "Another Name"

    # 5. Modifying URL while Checking: 409 Conflict
    res_url = await client.patch(f"/targets/{target_id}", json={"url": "https://93.184.216.34/another"})
    assert res_url.status_code == 409
    assert "currently being checked" in res_url.json()["detail"]

    # Verify URL was not changed in DB
    with api_session_factory() as db:
        target = db.get(Target, target_id)
        assert target is not None
        assert target.url == "https://93.184.216.34/updated"


async def test_update_target_guards_url_change_while_in_flight(
    client: httpx.AsyncClient,
    api_session_factory,
):
    from app.services.concurrency import _in_flight_targets

    target_id = await create_target(client)

    # Simulate in-flight target in background worker
    _in_flight_targets.add(target_id)
    try:
        res = await client.patch(f"/targets/{target_id}", json={"url": "https://93.184.216.34/new-url"})
        assert res.status_code == 409
        assert "currently being checked" in res.json()["detail"]
    finally:
        _in_flight_targets.discard(target_id)


async def test_paginated_targets_route(
    client: httpx.AsyncClient,
    api_session_factory,
):
    # 1. Empty state
    res_empty = await client.get("/targets/page")
    assert res_empty.status_code == 200
    data_empty = res_empty.json()
    assert data_empty["total"] == 0
    assert data_empty["items"] == []
    assert data_empty["limit"] == 50
    assert data_empty["offset"] == 0

    # 2. Seed 51 active targets and 2 inactive targets
    with api_session_factory() as db:
        for i in range(51):
            db.add(
                Target(
                    name=f"Active Target {i:02d}",
                    url=f"https://example.com/{i}",
                    is_active=True,
                )
            )
        for i in range(2):
            db.add(
                Target(
                    name=f"Inactive Target {i:02d}",
                    url=f"https://inactive.example.com/{i}",
                    is_active=False,
                )
            )
        db.commit()

    # 3. Page 1 (limit=50, offset=0, include_inactive=False default)
    res_p1 = await client.get("/targets/page?limit=50&offset=0")
    assert res_p1.status_code == 200
    data_p1 = res_p1.json()
    assert data_p1["total"] == 51
    assert len(data_p1["items"]) == 50
    assert data_p1["limit"] == 50
    assert data_p1["offset"] == 0

    # 4. Page 2 (limit=50, offset=50)
    res_p2 = await client.get("/targets/page?limit=50&offset=50")
    assert res_p2.status_code == 200
    data_p2 = res_p2.json()
    assert data_p2["total"] == 51
    assert len(data_p2["items"]) == 1

    # Ensure items on page 1 and page 2 do not overlap
    p1_ids = {t["id"] for t in data_p1["items"]}
    p2_ids = {t["id"] for t in data_p2["items"]}
    assert p1_ids.isdisjoint(p2_ids)

    # 5. include_inactive=True should include 51 + 2 = 53
    res_all = await client.get("/targets/page?include_inactive=true&limit=100")
    assert res_all.status_code == 200
    assert res_all.json()["total"] == 53
    assert len(res_all.json()["items"]) == 53


