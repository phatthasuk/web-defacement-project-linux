# Transient Screenshot Capture Retry

## Issue

Chromium can fail a full-page screenshot with the protocol error
`Page.captureScreenshot: Unable to capture screenshot`. The capture pipeline
classified it as an internal failure, so the persisted retry scheduler did not
retry it even when a later manual capture succeeded.

## Implementation

The capture layer now wraps only this specific Playwright screenshot protocol
failure in `ScreenshotCaptureError`. It maps to `screenshot_capture_failed` and
is eligible for one retry per run after 120 seconds plus the existing retry
jitter. The existing `CHECK_RETRY_MAX_ATTEMPTS` cap still limits all attempts
in the run. Prior screenshot failures are read from persisted `CheckAttempt`
records, so the screenshot-specific limit survives process restarts. Other
Playwright and internal errors remain non-retryable. SSRF blocks and capture
budget failures remain non-retryable.

The retry uses the existing durable attempt and progress flow. Both failed and
successful attempts remain in history. No schema or migration change was
needed. The scheduling summary in `plan/PROJECT_PLAN.md` now describes this
exception.

## Verification

Date: 2026-10-21, Asia/Bangkok. Environment: Windows development checkout,
Python 3.13.7. Source baseline: `f8c58904a1d0d59d6ee483a4e75134fd4232b773`
plus the local working-tree changes at verification time.

- `.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest-screenshot-retry-20261021-final -p no:cacheprovider tests/test_attempts.py tests/test_checks.py -q` — **52 passed**, 1 third-party Passlib deprecation warning.
- `.\.venv\Scripts\ruff.exe check --no-cache app tests scripts alembic` — passed.
- `.\.venv\Scripts\python.exe -m mypy --no-incremental --cache-dir=nul app` — no issues in 65 source files.
- Regressions cover recovery after one screenshot failure, stopping after a second screenshot failure, the 120-second deadline, persisted attempt history, and the exclusions for resource-budget, SSRF and generic internal errors.

Linux Docker runtime behavior, production Chromium logs and a capture against a
controlled browser page were not verified. The targeted tests use local fixture
databases and injected capture functions; they did not access `backend/data/` or
real websites. Next action: verify this bounded retry in the deployment-equivalent
Linux container using a controlled capture fixture before marking runtime
verification complete.
