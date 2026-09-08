# Visual / Pixel Diffing System Architecture & Implementation

**Date:** July 22, 2026  
**Document Name:** `VisualDiffingSystem-22-7-2026.md`  

---

## 1. Architectural Overview & Non-Blocking Execution

* **Core Diff Module:** Implemented in `compare_image_files()` within [`backend/app/services/diff/diff.py`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/diff/diff.py#L54-L86).
* **Concurrency Management:** In [`backend/app/services/checks.py`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/checks.py#L90), image comparison workloads (CPU-bound) are offloaded via `asyncio.to_thread()` to the thread pool, preventing them from blocking FastAPI's asynchronous event loop.

---

## 2. Image Comparison Algorithm & Implementation

### Step 1: Image Loading & Color Space Normalization
The engine loads the **Baseline Screenshot** (reference capture) and the **Current Screenshot** (latest evaluation capture) from disk using Pillow (`PIL.Image.open()`). Both images are normalized to the **RGB** color space (`image.convert("RGB")`) to ensure deterministic channel evaluation.

### Step 2: Canvas Normalization & Alignment
Because web pages may shift in vertical height or layout dimensions between runs, screenshots often differ in bounding box resolutions. The engine aligns them onto a shared canvas:
1. Determines maximum bounding dimensions:
   $$\text{canvas\_width} = \max(\text{baseline.width}, \text{current.width})$$
   $$\text{canvas\_height} = \max(\text{baseline.height}, \text{current.height})$$
2. Creates clean white (`"white"`) background canvases matching the bounding dimensions for both captures.
3. Pastes the baseline and current images onto their respective canvases anchored at `(0, 0)`.

### Step 3: Fast C-Extension Pixel Diffing (Pillow ImageChops)
To avoid high-overhead Python iteration loops, comparison relies on Pillow's underlying C extensions:
1. Calls `ImageChops.difference(baseline_canvas, current_canvas)` to compute absolute channel differences per pixel.
2. Deconstructs the difference image into individual R, G, B channels via `.split()`.
3. Merges the channels using `ImageChops.lighter()` to determine the maximum variance across channels per pixel (enforcing the principle that a pixel is flagged as changed if any color channel deviates).

### Step 4: Change Score Computation (`visual_change_score`)
1. Reads the composite difference histogram via `max_diff.histogram()[0]` to isolate unchanged pixels (zero difference).
2. Computes the quantity of mutated pixels:
   $$\text{changed\_pixels} = \text{total\_pixels} - \text{unchanged\_pixels}$$
3. Computes the proportional visual change score:
   $$\text{visual\_change\_score} = \frac{\text{changed\_pixels}}{\text{total\_pixels}}$$
   * Yields a normalized float bounded between `0.0` (zero modified pixels) and `1.0` (complete pixel mutation), rounded to 6 decimal places.

---

## 3. Decision Threshold & Status Evaluation

During target check execution ([`backend/app/services/checks.py`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/checks.py#L97-L101)):
* The `visual_change_score` is evaluated against `settings.VISUAL_CHANGE_THRESHOLD`.
* If either `visual_change_score` or `text_change_score` breaches its respective threshold, the system flags the target as **`Changed`** and commits the check result to the database.
