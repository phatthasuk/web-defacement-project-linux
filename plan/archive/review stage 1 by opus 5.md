# Review — Stage 1 Implementation

**Reviewed:** 2026-09-03
**Subject:** [`refinement/3-9-2026/Stage1-Implementation-3-9-2026.md`](../refinement/3-9-2026/Stage1-Implementation-3-9-2026.md) and the code it describes
**Plan reference:** [`plan/PROJECT_PLAN.md`](PROJECT_PLAN.md) Stage 1.1, 1.2, 1.3 and finding F5
**Reviewer:** Claude Opus 5
**Scope:** verification and review only. No source code was modified during this review.

---

## 1. Verdict

**The implementation is sound and the architecture is good.** Stage 1.1, 1.2 and
1.3 are genuinely delivered, the staging pipeline is clean, and one design
decision (keeping SSRF failures out of the availability classification) is
notably well judged.

Two things need attention before Stage 2 begins:

1. **`ruff` fails with 5 errors, and the summary document does not mention `ruff` at all.**
2. **The scheduler launches checks with an unreferenced `asyncio.create_task`,** which
   can drop a running check and silently swallows its exceptions — a poor property
   for a 2-4 week unattended soak whose entire purpose is collecting complete data.

The document also overstates two claims (periodic reconciliation, and the test
delta) that should be corrected so the record stays trustworthy.

---

## 2. Verification performed

All commands run from the repository on 2026-09-03.

| Gate | Command | Result |
| :--- | :--- | :--- |
| Backend tests | `python -m pytest -q` | **109 passed**, 2 warnings |
| Backend types | `python -m mypy app` | **clean** (46 source files) |
| Backend lint | `python -m ruff check .` | **5 errors** |
| Frontend tests | `npx vitest run` | **34 passed** (7 files) |
| Frontend lint | `npx eslint .` | **0 errors**, 1 pre-existing warning (`useAuth.tsx:91`) |

---

## 3. Claims confirmed accurate

| Claim in the summary | Verified |
| :--- | :--- |
| 109 pytest passing | Yes |
| 34 vitest passing (was 33) | Yes |
| `app/services/scheduler.py` and `tests/test_scheduler.py` created | Yes (131 / 113 lines) |
| `STATUS_AVAILABILITY_ISSUE` with transitions `Checking -> AI`, `AI -> Checking`, `AI -> OK` | Yes (`app/core/status.py:9,23,28`) |
| Staging pipeline writes to `data/staging/{snapshot_id}/` and discards on `OK` | Yes (`app/services/checks.py:296-317`) |
| `reconcile_artifacts` confines every deletion to `DATA_DIR` | Yes — `is_relative_to(data_dir)` is checked in both the staging loop and the orphan loop (`app/services/checks.py:512`) |
| New settings for interval, jitter and staging age | Yes (`app/core/config.py:43-47`) |
| Frontend `Availability Issue` badge, type and test | Yes |

### Worth calling out as good work

`is_availability_error` (`app/services/checks.py:47`) **explicitly excludes
`SsrfBlockedError`**, and checks both the exception type and the message text:

```python
if isinstance(exc, SsrfBlockedError):
    return False
...
if "blocked by ssrf guard" in msg:
    return False
```

Softening a blocked SSRF attempt into "the site was briefly unavailable" would
have quietly demoted a security event. Catching that boundary deliberately, and
defending it twice, is the right instinct.

The staging-then-promote-or-discard structure is also a clean solution to F5: a
single `_discard_snapshot_files(capture)` in the `except` path covers every
failure mode, rather than scattering cleanup through the happy path.

---

## 4. Issues

### 4.1 `ruff` fails, and the summary does not report it — **must fix**

```
app/services/checks.py:56:8       UP038  Use `X | Y` in isinstance instead of (X, Y)
app/services/concurrency.py:165   E501   Line too long (105 > 100)
tests/test_scheduler.py:1:8       F401   `asyncio` imported but unused
tests/test_scheduler.py:11:46     F401   `STATUS_OK` imported but unused
tests/test_status.py:1:1          I001   Import block is un-sorted
```

Three are fixable with `ruff check --fix`.

The larger problem is the reporting gap. Section 6 of the summary lists only
pytest, vitest and the production build. The Phase A record from 2026-09-02
listed ruff, mypy, tsc and eslint. Dropping gates from the report means a
failing gate is invisible to anyone who trusts the document.

**Recommendation:** report the same fixed set of gates every time —
`pytest`, `ruff`, `mypy`, `vitest`, `tsc`, `eslint` — including the ones that pass.

### 4.2 Fire-and-forget task in the scheduler — **fix before Stage 2**

`app/services/scheduler.py:125`:

```python
asyncio.create_task(
    run_checks_for_targets([target.id], self.settings, session_factory=self.session_factory)
)
```

The task reference is discarded. Three consequences:

- **The task can be garbage-collected mid-run.** The event loop keeps only weak
  references to tasks; the CPython documentation explicitly warns to retain a
  reference. A check could vanish part-way through, at random.
- **Exceptions are never retrieved.** A check that raises inside the task fails
  silently; the error only ever surfaces as a late "Task exception was never
  retrieved" message at garbage-collection time.
- **Shutdown does not wait for in-flight checks.** `stop()` (line 53) cancels only
  `self._task`, the loop itself. A check running at shutdown is abandoned, leaving
  its target in `Checking`. `recover_stale_checks` then flips it to `Failed` on the
  next start — self-healing, but `Failed` misrepresents what happened, and it will
  pollute the Stage 2 failure-rate measurement.

There is already an observable symptom in the test suite:

```
RuntimeWarning: coroutine 'run_checks_for_targets.<locals>.worker' was never awaited
  tests/test_scheduler.py::test_scheduler_skips_target_already_checking
```

Warning count rose from 1 to 2 with this change. A scheduler test starts a real
background check that is never awaited and is dropped when the loop closes.

**Why this matters now:** Stage 2 is a 2-4 week unattended soak whose only
purpose is to produce trustworthy measurements. A scheduler that can silently
lose checks undermines exactly that.

**Suggested shape of the fix:** hold the tasks in a set, discard on completion,
log any exception, and await or cancel the set in `stop()`.

---

## 5. Document does not match the code

### 5.1 "Startup **and periodic** reconciliation" — periodic does not exist

`reconcile_artifacts` has exactly one call site: `app/main.py:47`, inside the
lifespan startup. The scheduler never calls it.

Over a multi-week soak with no restart, staging directories left by crashed
captures accumulate until the next restart. Low impact, but the claim is not true
as written. Either wire it into the scheduler loop or reword the document.

**If it is made periodic, note the race it introduces:** the orphan sweep deletes
any file under `screenshots/`, `text/` or `html/` whose stem is not in
`Snapshot.id`. Artifacts are promoted to those directories before the snapshot row
is committed, so a sweep running at that instant would delete a live check's
files. Running only at startup avoids this today.

### 5.2 The "before" test count is wrong

The summary states **"Backend Tests: 73 passed -> 109 passed, +36"**.

73 was the count two rounds of work earlier. The actual count immediately before
Stage 1 was **99**, recorded in `PROJECT_PLAN.md` section 3 — 73 plus 9 from
multi-baseline matching and 17 from the structural detector.

**The real delta is +10, not +36.** The work is real; the arithmetic inflates it
by a factor of 3.6 and should be corrected.

### 5.3 `SCHEDULER_POLL_INTERVAL_SECONDS` is undocumented

`app/core/config.py:46` sets it to 15 seconds and it governs how often the loop
wakes. Section 2 of the summary describes the interval and jitter but not this,
so anyone tuning the scheduler would not know it exists.

---

## 6. Design observations

Not defects — decisions worth recording so they are not rediscovered later.

### 6.1 An `OK` check no longer references what was captured

`app/services/checks.py:302` sets `current_snapshot_id = matched_baseline_id` for
unchanged checks, because the capture has just been discarded.

Consequences worth writing down:

- **No evidence survives from quiet periods.** If a compromise is discovered later,
  there is no record of how the page looked during the hours it reported `OK`.
  Baselines still exist, so this is a reduction in forensic depth, not a loss of
  the reference point.
- **The row is internally inconsistent to a reader.** It can carry a non-zero
  `visual_change_score` while both snapshot ids are identical, so the Check Detail
  page shows "no differences" beside a non-zero score.

This is the accepted Stage 1.2 trade-off, but the summary presents it purely as a
gain ("100% reduction"). The cost belongs in the record too.

### 6.2 A compromised site that returns 5xx is now silent

HTTP 5xx becomes `Availability Issue`, the staged files are discarded, and under
the Stage 3 notification policy sketched in the plan, availability issues do not
notify. An attacker who takes a site down — or whose payload makes it 500 — would
therefore produce no alert and no stored evidence.

Separating availability from change is still correct; this is not a Stage 1
defect. It is a **requirement for Stage 3**: a sustained or repeated
`Availability Issue` must escalate on its own. A hospital site unreachable for
hours is an incident regardless of cause.

### 6.3 A skipped check waits a full interval

In `_tick`, the next due time is advanced at line 108, **before** the in-flight
check at line 112. A target skipped because a check is already running is pushed
out by a whole `CHECK_INTERVAL_SECONDS`, rather than being retried shortly after.
At an hourly interval that silently drops a data point.

### 6.4 Availability classification relies on substring matching

`is_availability_error` matches lowercased substrings of the exception message
(`"timeout"`, `"network error"`, `"gaierror"`, …). This works because the messages
come from Playwright and from our own error types, but it is fragile: any future
error text containing one of these words will be reclassified. The type checks are
robust; the string list is the soft part.

*(Minor: `isinstance(exc, (TimeoutError, asyncio.TimeoutError))` is redundant on
Python 3.11+, where `asyncio.TimeoutError` is an alias of `TimeoutError`. This is
also the line ruff flags as UP038.)*

---

## 7. Recommended actions before starting Stage 2

| Priority | Action |
| :--- | :--- |
| **1** | Fix the scheduler's fire-and-forget tasks: retain references, log exceptions, drain on shutdown (section 4.2) |
| **2** | Fix the 5 ruff errors and resolve the un-awaited-coroutine warning in `test_scheduler.py` |
| **3** | Correct the summary: the "before" count is 99, not 73 (+10, not +36) |
| **4** | Correct or implement the "periodic reconciliation" claim |
| **5** | Adopt a fixed verification checklist in every refinement document: pytest, ruff, mypy, vitest, tsc, eslint |
| 6 | Record observations 6.1 and 6.2 in `PROJECT_PLAN.md` — 6.1 under accepted trade-offs, 6.2 as a Stage 3 requirement |
| 7 | Document `SCHEDULER_POLL_INTERVAL_SECONDS`; consider retrying a skipped check sooner than a full interval |

Items 1 and 2 are the only ones that block Stage 2. The rest are record-keeping
and can be done alongside it.

---

## 8. Scope and limits of this review

- Verified by running the test, lint and type gates listed in section 2, and by
  reading `scheduler.py`, the modified parts of `checks.py`, `status.py`,
  `config.py` and `main.py`.
- **Not verified:** the scheduler has not been observed running against live
  targets over time, so jitter distribution, interval drift and behaviour under
  repeated failures are untested in practice. Stage 2 is itself that test.
- **Not verified:** actual disk savings were not measured against a real run. The
  "0 bytes for unchanged checks" claim follows from reading the code and is
  covered by unit tests, but no multi-day figure exists yet — it is one of the
  things Stage 2 is meant to measure.
