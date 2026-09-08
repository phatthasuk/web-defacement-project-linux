# Milestone 5 Development Plan — SSRF Guard (Backend Core)

*Handoff document. Builds on `app/services/capture/capture.py::capture_snapshot`, `app/core/config.py::Settings` (which already defines `ALLOWED_SCHEMES`/`allowed_schemes_list`, unused today), and the failure-propagation path already established in `app/services/checks.py::run_target_check` and `app/services/concurrency.py`. Corresponds to the SSRF portion of Milestone 5 in [plan/prototype-plan.md](prototype-plan.md) §10/§11.*

## 1. Goal

Nothing today stops `capture_snapshot()` from being pointed at `http://169.254.169.254/` or `http://10.0.0.5/`. That's fine while no HTTP route exists to submit a URL, but it must be closed *before* the upcoming API-wiring milestone opens `POST /targets` to callers — per §10, this is a required prototype guard, not an optional hardening step.

## 2. Scope

**In scope** (from §10's required list)
- Scheme allowlist (`http`/`https` only — reuse `Settings.allowed_schemes_list`, already defined, currently unused).
- Block private/loopback/link-local ranges and cloud-metadata addresses (`169.254.169.254` falls under link-local, no special-case needed).
- Re-check DNS **after redirects**, not just on the initial URL — the trickiest item, detailed in §5 below.
- Basic error handling specific to this guard: a distinct exception type so a blocked URL is unambiguous in logs/`TargetCheckResult.error`, not indistinguishable from a generic capture failure.
- Fixture pages/tests needed to exercise the guard itself (not the general fixture-page backlog).

**Out of scope / deferred**
- The smoke-test script from §11's Milestone 5 list — deferred to the API-wiring milestone, where it's actually meaningful to run end-to-end against real routes (see prior discussion). Milestone 5 here is scoped to the SSRF guard specifically.
- Full network sandboxing (containers, egress firewalls) — explicitly **not required** for the prototype per §10.
- Encrypted credential/`storage_state` profiles, authenticated target login — explicitly **not required** per §10.

## 3. Decisions locked before/while building

1. **Always validate the resolved IP address, never the original hostname string.** This is the one principle that makes the whole guard robust against format tricks (decimal/octal/hex IP notation, IPv6-mapped-IPv4, etc.) without hand-rolling a parser for each: whatever string the attacker puts in the URL, `socket.getaddrinfo()` resolves it to a concrete IP, and every resolved IP is what gets checked against the blocklist. No special-casing of "suspicious-looking hostnames" needed.
2. **Validation is a plain, framework-agnostic function — not something bolted only onto Playwright.** It needs to be callable two ways: (a) standalone, before any browser is involved, for the future `POST /targets` creation-time check ("fail fast, don't let a bad target sit in the queue" — production plan §15.2); and (b) from inside `capture_snapshot`, per redirect hop. One shared function in `app/core/ssrf_guard.py`, not duplicated logic in the capture module.
3. **Redirect re-validation happens via Playwright's request interception (`page.route`), scoped to navigation requests only.** Checking every sub-resource request (images, CSS, scripts the target page loads) would be closer to full network sandboxing, which §10 explicitly excludes from the prototype. Scoping to `request.is_navigation_request()` matches exactly what §10 asks for ("re-check DNS after redirects" — redirects only happen on navigation requests) and keeps the guard cheap.
4. **Bundle redirect-count enforcement into the same interception point.** Today, `REDIRECT_LIMIT` is only checked *after* `page.goto()` returns, by walking `request.redirected_from` — meaning Playwright has already followed however many redirects a malicious/misconfigured server sent before the limit is enforced. Since the guard is already intercepting every navigation request, counting hops there and aborting once `REDIRECT_LIMIT` is exceeded closes that gap essentially for free. The existing post-hoc count can stay as a defensive double-check.

## 4. New module: `app/core/ssrf_guard.py`

- `SsrfBlockedError(CaptureError)` — subclassing the existing `CaptureError` from `capture.py` (or a shared base both inherit) so it flows through `run_target_check`'s existing `except Exception` failure path with **no changes needed** in `checks.py` or `concurrency.py`. The only difference from a generic capture failure is that the message is unambiguous ("blocked by SSRF guard: resolved to private address X") instead of "navigation failed."
- `validate_scheme(url: str, settings: Settings) -> None` — parse with `urlparse`, reject anything not in `settings.allowed_schemes_list`.
- `resolve_host_ips(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]` — wraps `socket.getaddrinfo(hostname, None)`, returns every distinct resolved address as an `ipaddress` object. Raises `SsrfBlockedError` if resolution fails (fail closed, not open).
- `is_blocked_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool` — for IPv6, first unmap IPv4-mapped addresses via `.ipv4_mapped` and classify the unmapped form; otherwise check `is_private`, `is_loopback`, `is_link_local`, `is_reserved`, `is_multicast`, `is_unspecified`. This covers 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16 (cloud metadata included), `::1`, `fc00::/7`, `fe80::/10`, and IPv4-mapped-IPv6 variants of all of the above — via Python's own `ipaddress` classification rather than a hand-maintained CIDR list, which is both more reliable and less to maintain.
- `validate_url(url: str, settings: Settings) -> None` — the single entry point: `validate_scheme` then `resolve_host_ips` then reject if **any** resolved address is blocked (not just the first — a hostname can resolve to multiple IPs).

## 5. Wiring into `capture_snapshot` (`app/services/capture/capture.py`)

- **Up front**: call `validate_url(url, settings)` before `browser.new_page()` — fails fast for the common case without even launching a page.
- **Per redirect hop (DNS rebinding protection)**: before `page.goto(...)`, register `page.route("**/*", handler)` where `handler`:
  - Passes through immediately (`route.continue_()`) if `not request.is_navigation_request()` — decision #3, keeps sub-resource loads untouched.
  - For navigation requests: increment a hop counter; if it exceeds `settings.REDIRECT_LIMIT`, `route.abort()` and raise `SsrfBlockedError` (decision #4).
  - Otherwise, call `validate_url(request.url, settings)`; if it raises, `route.abort()` and propagate `SsrfBlockedError` out of the `goto()` call instead of letting navigation proceed.
  - This naturally re-validates the *initial* request too (belt-and-suspenders with the up-front check) and every subsequent redirect hop the server sends — exactly the "DNS rebinding: resolve returns a public IP on first check, private IP on a later hop" scenario from the production plan's test list.

## 6. Sequencing

1. `app/core/ssrf_guard.py` — pure validation functions, no Playwright dependency, unit-testable in isolation with mocked `socket.getaddrinfo`.
2. Up-front `validate_url()` call in `capture_snapshot`, before page creation.
3. `page.route()` interception for per-hop re-validation + redirect counting.
4. Tests (the pure-function tests in step 1 can and should be written alongside it, before steps 2–3 land).

## 7. Test plan

- **Scheme rejection**: `file://`, `ftp://`, `javascript:` URLs rejected before any DNS resolution is attempted.
- **Private-range blocking**: table-driven test over representative addresses — `127.0.0.1`, `10.0.0.5`, `172.16.0.1`, `192.168.1.1`, `169.254.169.254` (cloud metadata), `::1`, `fc00::1`, `fe80::1` — all rejected; a normal public IP accepted.
- **Obfuscated-format bypass attempts**: decimal (`2130706433`), octal/hex IPv4 notation, and IPv4-mapped-IPv6 (`::ffff:127.0.0.1`) — all must resolve down to a blocked address and be rejected, proving decision #1 holds without format-specific parsing.
- **DNS rebinding simulation**: mock `socket.getaddrinfo` to return a public IP on the first call and a private IP on a subsequent call (simulating a hostname that rebinds between the initial check and a redirect hop) — assert the guard catches it on the second resolution, not just the first.
- **Redirect-hop re-validation end-to-end**: using Playwright against a local fixture (a small test server or `page.route`-mocked redirect chain) where hop 2 points at a blocked address — assert the capture is aborted with `SsrfBlockedError`, not silently followed.
- **Redirect-count enforcement moved earlier**: a redirect chain longer than `REDIRECT_LIMIT` is aborted at the hop-counting stage, not only detected after the fact.
- **Failure propagation**: `run_target_check` given a target whose URL fails `validate_url` ends in `STATUS_FAILED` with a clear, distinguishable error message — reuses existing failure-path tests from Milestone 3/4 as a pattern, no new status or transition needed.

## 8. Definition of done

- All tests above pass under `pytest`.
- `ruff check .` and `mypy .` clean.
- `capture_snapshot` rejects every blocked-address case in the test matrix and still succeeds against real public sites (manual sanity check against `https://example.com`, as done in Milestone 1 verification).
- No changes required to `checks.py` or `concurrency.py` — confirms the "flows through existing failure handling" design goal held.

## 9. Handoff notes

- `Settings.ALLOWED_SCHEMES` / `allowed_schemes_list` already exist in `app/core/config.py` — this milestone is the first thing to actually read them.
- `validate_url()` is written to be reusable, framework-agnostic, and synchronous specifically so the upcoming `POST /targets` route can call it at creation time without needing a browser — don't couple it to Playwright types.
- After this lands, the two items still open from earlier handoffs are: the API-routes-wiring milestone (now the natural next step, with the deferred smoke-test script folded into its verification) and the remaining §10 items not covered here ("basic error handling" beyond the SSRF-specific case, if any further gaps turn up once routes exist).
