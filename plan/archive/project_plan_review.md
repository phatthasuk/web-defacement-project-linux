# Technical Review & Feedback: Change-Detection / Integrity Monitoring System

This project plan is comprehensively designed and reflects a strong, production-grade awareness of the practical challenges inherent to Change-Detection and Integrity Monitoring systems. Decoupling the architecture into separate layers—namely the Scheduler, Worker (Playwright), and Diff Engine—ensures excellent scalability for future expansions.

Below are technical insights and additional considerations for each component to enhance system stability and better handle edge cases:

---

## 1. Architecture and Tech Stack Analysis

* **FastAPI + Playwright (Async) + Celery:** This architecture is exceptionally well-suited for high-concurrency and I/O-bound workloads. Offloading heavy processing tasks to Celery Workers effectively prevents performance bottlenecks at the API Gateway.
* **S3-Compatible Storage (MinIO/S3):** Separating screenshots and raw HTML files from the relational database is the correct approach. It prevents PostgreSQL database bloat caused by handling large binary objects (Blobs), maintaining database efficiency over time.

---

## 2. Deep Dive into Challenges and Optimizations

### 3.3 & 3.6 Headless Browser Memory Management (Memory Leak Mitigation)
Although Playwright is highly stable, repeatedly opening and closing browser contexts or instances thousands of times within a Celery Worker often leads to memory leaks at the operating system level.
* **Recommendation:** Implement a Worker Recycling strategy in Celery (e.g., configuring `worker_max_tasks_per_child`) to force-spawn a new process after a specific number of tasks, releasing memory back to the OS. Alternatively, design the worker to keep a single browser instance open while creating new contexts for each task, but schedule a browser restart every $N$ jobs.

### 3.4 & 6.1 False-Positive Management and "Ignore-Region" Methods
Normalizing HTML to strip elements like CSRF tokens or timestamps works to some extent for DOM diffing. However, for visual/pixel diffing (SSIM/pHash), dynamic elements such as sliders, randomized ad banners, or weather widgets pose a significant challenge.
* **Recommendation (Visual Masking):** Instead of relying solely on raw pixel comparison, implement a feature that passes `ignore_selectors` (e.g., `#dynamic-banner`, `.footer-timestamp`) to Playwright before taking screenshots. This can be achieved by injecting CSS to hide these elements (`display: none !important;`) or drawing black bounding boxes over the designated regions on a canvas before passing the image to the SSIM/pHash engine.

### 3.5 Alerting Severity Model & Security-Signal
Utilizing rule-based heuristics (No-AI) for security checks is a major strength, providing rapid execution and predictable behavior. The following checkpoints should be integrated into the detection rules:
* **CSP (Content Security Policy) Changes:** Monitor whether CSP HTTP headers are altered, weakened, or completely removed.
* **Third-Party Script Allowlist:** In addition to verifying the DOM structure, maintain a list of permitted external domains. If a `<script src="...">` tag referencing an unlisted domain is detected, escalate the alert severity to High immediately.

### 6.5 "Down" vs. "Defaced" Status (Race Conditions)
Target CMS platforms or web boards may occasionally experience transient slowness, resulting in Playwright timeouts or broken page layouts due to assets (CSS/JS) failing to load in time. This can cause false alarms that mimic website defacement.
* **Recommendation (Retry Logic):** Before triggering a "Defaced" alert, implement a double-check phase. Route the task to a specialized retry queue for immediate re-verification by another worker (e.g., retrying after a 1–2 minute delay). Confirm the alert only if the divergence still exceeds the threshold, thereby mitigating alert fatigue for system administrators.

---

## 3. Feedback on Build Phases

The planned sequence (Phases 1 through 7) is logical and establishes a solid Agile approach by prioritizing the core engine first. However, it is highly recommended to reorder certain tasks:
* **Phase Adjustment:** The implementation of **Normalization/Ignore-regions** (originally in Phase 7) should be brought forward to Phase 2 or 3, immediately following the introduction of multi-detector diffing. Without baseline noise exclusion, subsequent testing phases will be severely hindered by continuous false-positive noise from the detectors.

---
