from pathlib import Path
from uuid import uuid4

from PIL import Image

from app.services.diff import compare_image_files, compare_snapshot_artifacts, compare_text_files


def test_compare_text_files_scores_changed_text(tmp_path: Path):
    work_dir = make_work_dir(tmp_path)
    baseline = work_dir / "baseline.txt"
    current = work_dir / "current.txt"
    baseline.write_text("Welcome to the site", encoding="utf-8")
    current.write_text("Hacked by attacker", encoding="utf-8")

    score = compare_text_files(baseline, current)

    assert 0.0 < score <= 1.0


def test_compare_image_files_scores_pixel_changes(tmp_path: Path):
    work_dir = make_work_dir(tmp_path)
    baseline = work_dir / "baseline.png"
    current = work_dir / "current.png"
    Image.new("RGB", (10, 10), "white").save(baseline)
    image = Image.new("RGB", (10, 10), "white")
    image.putpixel((0, 0), (0, 0, 0))
    image.save(current)

    score = compare_image_files(baseline, current)

    assert score == 0.01


def test_compare_image_files_counts_single_channel_changes(tmp_path: Path):
    work_dir = make_work_dir(tmp_path)
    baseline = work_dir / "baseline.png"
    current = work_dir / "current.png"
    Image.new("RGB", (10, 10), "black").save(baseline)
    image = Image.new("RGB", (10, 10), "black")
    # Only the red channel differs; a luminance-based reduction would round this
    # away, so this guards the "any channel differs" semantic.
    image.putpixel((0, 0), (1, 0, 0))
    image.save(current)

    score = compare_image_files(baseline, current)

    assert score == 0.01


def test_compare_snapshot_artifacts_summarizes_no_change(tmp_path: Path):
    work_dir = make_work_dir(tmp_path)
    baseline_text = work_dir / "baseline.txt"
    current_text = work_dir / "current.txt"
    baseline_image = work_dir / "baseline.png"
    current_image = work_dir / "current.png"

    baseline_text.write_text("same", encoding="utf-8")
    current_text.write_text("same", encoding="utf-8")
    Image.new("RGB", (2, 2), "white").save(baseline_image)
    Image.new("RGB", (2, 2), "white").save(current_image)

    result = compare_snapshot_artifacts(
        str(baseline_text),
        str(current_text),
        str(baseline_image),
        str(current_image),
    )

    assert result.text_change_score == 0.0
    assert result.visual_change_score == 0.0
    # No HTML artifacts were passed, so the structural detector stays silent.
    assert result.structure_change_score == 0.0
    assert result.summary == "No text, visual or structural changes detected."


def make_work_dir(tmp_path: Path) -> Path:
    work_dir = tmp_path / f"diff-{uuid4()}"
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def test_compare_text_files_handles_large_text_fast(tmp_path: Path):
    import time
    work_dir = make_work_dir(tmp_path)
    baseline = work_dir / "baseline.txt"
    current = work_dir / "current.txt"

    text_1 = "Some baseline line content.\n" * 6000
    text_2 = "Some baseline line content.\n" * 5900 + "Some changed line content.\n" * 100

    baseline.write_text(text_1, encoding="utf-8")
    current.write_text(text_2, encoding="utf-8")

    start_time = time.perf_counter()
    score = compare_text_files(baseline, current)
    duration = time.perf_counter() - start_time

    assert duration < 0.2
    assert 0.0 < score < 1.0

