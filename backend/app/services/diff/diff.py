import logging
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops

from app.services.diff.structure import StructureDiff, compare_structure, extract_structure

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiffResult:
    text_change_score: float
    visual_change_score: float
    summary: str
    # Third detector: see app.services.diff.structure. Defaults keep older
    # callers and snapshots without an HTML artifact working.
    structure_change_score: float = 0.0
    structure_summary: str = ""
    structure_added: tuple[str, ...] = ()
    structure_removed: tuple[str, ...] = ()


def compare_snapshot_artifacts(
    baseline_text_path: str,
    current_text_path: str,
    baseline_screenshot_path: str,
    current_screenshot_path: str,
    baseline_html_path: str | None = None,
    current_html_path: str | None = None,
    baseline_url: str = "",
    current_url: str = "",
    allowed_hosts: Collection[str] = (),
) -> DiffResult:
    text_score = compare_text_files(Path(baseline_text_path), Path(current_text_path))
    visual_score = compare_image_files(
        Path(baseline_screenshot_path),
        Path(current_screenshot_path),
    )

    structure = compare_html_files(
        baseline_html_path,
        current_html_path,
        baseline_url=baseline_url,
        current_url=current_url,
        allowed_hosts=allowed_hosts,
    )

    return DiffResult(
        text_change_score=text_score,
        visual_change_score=visual_score,
        summary=summarize_diff(text_score, visual_score, structure.score, structure.summary),
        structure_change_score=structure.score,
        structure_summary=structure.summary,
        structure_added=structure.added,
        structure_removed=structure.removed,
    )


def compare_html_files(
    baseline_html_path: str | None,
    current_html_path: str | None,
    baseline_url: str = "",
    current_url: str = "",
    allowed_hosts: Collection[str] = (),
) -> StructureDiff:
    """Structural comparison of two stored HTML artifacts.

    A missing or unreadable artifact yields "no change" rather than an error: a
    baseline captured before this detector existed must not turn every check
    into a failure. It does mean the structural detector is silent for those
    snapshots, which is why the summary distinguishes the two cases.
    """
    if not baseline_html_path or not current_html_path:
        return StructureDiff(score=0.0, summary="Structural comparison unavailable.")

    try:
        baseline_html = Path(baseline_html_path).read_text(encoding="utf-8", errors="replace")
        current_html = Path(current_html_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        logger.warning("Could not read an HTML artifact; skipping structural comparison")
        return StructureDiff(score=0.0, summary="Structural comparison unavailable.")

    baseline_facts = extract_structure(baseline_html, baseline_url, allowed_hosts)
    current_facts = extract_structure(current_html, current_url, allowed_hosts)
    return compare_structure(baseline_facts, current_facts)


def compare_text_files(baseline_path: Path, current_path: Path) -> float:
    from difflib import SequenceMatcher

    baseline_text = baseline_path.read_text(encoding="utf-8")
    current_text = current_path.read_text(encoding="utf-8")
    if baseline_text == current_text:
        return 0.0

    # Cap diff cost: use line-based if either text is >= 100 KB
    baseline_len = len(baseline_text.encode("utf-8"))
    current_len = len(current_text.encode("utf-8"))
    if baseline_len >= 100 * 1024 or current_len >= 100 * 1024:
        baseline_lines = baseline_text.splitlines()
        current_lines = current_text.splitlines()
        ratio = SequenceMatcher(a=baseline_lines, b=current_lines).ratio()
    else:
        ratio = SequenceMatcher(a=baseline_text, b=current_text).ratio()

    return round(1.0 - ratio, 6)


def compare_image_files(baseline_path: Path, current_path: Path) -> float:
    with Image.open(baseline_path) as baseline_image:
        baseline = baseline_image.convert("RGB")
    with Image.open(current_path) as current_image:
        current = current_image.convert("RGB")

    canvas_size = (
        max(baseline.width, current.width),
        max(baseline.height, current.height),
    )
    baseline_canvas = Image.new("RGB", canvas_size, "white")
    current_canvas = Image.new("RGB", canvas_size, "white")
    baseline_canvas.paste(baseline, (0, 0))
    current_canvas.paste(current, (0, 0))

    diff = ImageChops.difference(baseline_canvas, current_canvas)

    # Collapse the per-channel difference into a single band whose pixel value is
    # the largest channel difference. This keeps the "a pixel changed if any RGB
    # channel differs" semantic while staying entirely in Pillow's C paths, instead
    # of iterating pixels in Python (which blocked the event loop and scaled badly
    # with full-page screenshots).
    bands = diff.split()
    max_diff = bands[0]
    for band in bands[1:]:
        max_diff = ImageChops.lighter(max_diff, band)

    total_pixels = canvas_size[0] * canvas_size[1]
    unchanged_pixels = max_diff.histogram()[0]
    changed_pixels = total_pixels - unchanged_pixels
    if changed_pixels <= 0:
        return 0.0
    return round(changed_pixels / total_pixels, 6)


def summarize_diff(
    text_change_score: float,
    visual_change_score: float,
    structure_change_score: float = 0.0,
    structure_summary: str = "",
) -> str:
    if text_change_score == 0.0 and visual_change_score == 0.0 and structure_change_score == 0.0:
        return "No text, visual or structural changes detected."

    summary = (
        f"Detected text change score {text_change_score:.4f}, "
        f"visual change score {visual_change_score:.4f} "
        f"and structural change score {structure_change_score:.4f}."
    )
    # Name the structural findings inline: they identify the specific script or
    # iframe involved, which is what an operator needs to triage an alert.
    if structure_change_score > 0.0 and structure_summary:
        summary = f"{summary} {structure_summary}"
    return summary
