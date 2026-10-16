# Text Diffing System Architecture & Implementation

**Date:** July 22, 2026  
**Document Name:** `TextDiffingSystem-22-7-2026.md`  

---

## 1. Architectural Overview & Text Capture

* **Capture Pipeline:** Executed via Playwright in [`backend/app/services/capture/capture.py`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/capture/capture.py#L128).
* **Text Extraction:** Uses `await page.inner_text("body")` after JavaScript execution settles into the `networkidle` state.
* **Data Characteristics:** Extracts visible rendered text only, excluding HTML tags, CSS stylesheets, and script bodies. Stored as an isolated `.txt` artifact for each snapshot.

---

## 2. Text Diffing Algorithm

The primary comparison engine is implemented in `compare_text_files()` within [`backend/app/services/diff/diff.py`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/diff/diff.py#L33-L52), following a multi-step evaluation:

### Step 1: Exact Match Short-Circuit
* Loads UTF-8 text contents from baseline and current snapshot files.
* If `baseline_text == current_text`, returns a change score of `0.0` immediately without further computation.

### Step 2: Adaptive Diffing Strategy (SequenceMatcher Scaling)
Because `difflib.SequenceMatcher` incurs significant computational complexity on long text strings, the engine employs a size-adaptive strategy:

1. **Small Files (< 100 KB):**
   * Executes character-level comparison:
     `ratio = SequenceMatcher(a=baseline_text, b=current_text).ratio()`
   * Delivers high granularity, detecting minor single-character or word mutations.

2. **Large Files (>= 100 KB):**
   * Falls back to line-level comparison:
     Splits text via `splitlines()` before passing to `SequenceMatcher`.
   * Mitigates CPU bottlenecks, processing large documents rapidly.

### Step 3: Change Score Computation (`text_change_score`)
* Derived from the similarity ratio:
  $$\text{text\_change\_score} = 1.0 - \text{ratio}$$
* Returns a floating-point score rounded to 6 decimal places, bounded between `0.0` (identical content) and `1.0` (completely disjoint text).

---

## 3. Evaluation & Threshold Enforcement

* The `text_change_score` feeds directly into the check evaluation engine in [`backend/app/services/checks.py`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/checks.py#L97).
* If `text_change_score > TEXT_CHANGE_THRESHOLD`, the system flags an unexpected text modification and transitions the target to **`Changed`**.
