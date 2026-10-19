# Phase 5: Linux Container Runtime Verification

**Parent plan:** [Remediation_Plan_19-10-2026.md](Remediation_Plan_19-10-2026.md)  
**Status:** Hardening changes are implemented; runtime verification remains open.  
**Last recorded environment:** Windows development host; Docker Desktop Linux engine was unavailable.

## Purpose and scope

Phase 5 verifies behavior that cannot be established by static checks or Windows-only tests. Run these checks on a Linux host with Docker Engine, using the deployment-compatible Compose configuration.

The phase covers:

- **B-01:** WebRTC UDP egress from Chromium.
- **B-09b:** POSIX directory file-descriptor and symlink cleanup behavior.
- **B-07 / B-10:** Container resource limits and Chromium/seccomp compatibility.
- **F-08 / F-09c:** Nginx security headers, canonical redirects, and production API routing.

## Preconditions

1. Use a Linux host with Docker Engine and Docker Compose available.
2. Use the deployment Compose file and the same Chromium image/version intended for deployment; record the image digest and browser version.
3. Set deployment variables, including `PUBLIC_HOST`, and save the effective Compose configuration with secrets redacted.
4. Use an isolated test network and a controlled STUN/UDP listener for WebRTC. Capture traffic at the container/host boundary so the result measures egress rather than only browser logs.
5. Keep the current seccomp profile for the baseline run. Change syscall allowances only as a separate experiment after collecting baseline evidence.

## Verification checklist

### 1. B-01 — WebRTC UDP egress

1. Start the Chromium capture container with the configured launch arguments, including `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` and `--enforce-webrtc-ip-handling-policy`.
2. Record the Chromium version and effective browser launch arguments.
3. Run a controlled page that creates an `RTCPeerConnection` and attempts to reach the test STUN/UDP listener through the expected proxy route and through a direct non-proxied route.
4. Capture packets at the listener and container/host egress boundary.

**Pass criteria:** Expected proxied behavior works; the direct non-proxied attempt produces no UDP packet at the external listener or egress boundary. Keep the test page, network topology, packet capture, and browser logs as evidence. A browser error alone is insufficient.

### 2. B-09b — POSIX cleanup and path safety

Run from `backend/`:

```bash
python -m pytest tests/test_cleanup_artifacts.py -v
```

Confirm the tests using `os.open()` with directory file descriptors and symlink rejection execute on Linux, alongside the database/output collision and lock-failure regressions.

**Pass criteria:** All 9 cleanup tests pass on Linux, including the two cases that depend on POSIX `dir_fd` and symlink behavior. Confirm the database, its sidecars, and approved artifacts remain protected.

### 3. B-07 / B-10 — Compose resource limits and seccomp

1. Validate and start the stack:

   ```bash
   docker compose config
   docker compose up -d --build
   ```

2. Inspect each relevant container and record its effective memory, CPU, and PID limits (`Memory`, `NanoCpus`, and `PidsLimit`).
3. Run capture/browser tests under the configured seccomp profile; check that Chromium starts, captures pages, and shuts down without syscall-denial failures.
4. After the baseline passes, test a candidate profile with `ptrace` and `io_uring_*` allowances removed. Keep the current profile if Chromium or required workloads fail.

**Pass criteria:** Effective limits match the Compose configuration. The browser workload passes under the chosen seccomp profile, with no unexplained crashes or denied required syscalls. Record any profile diff and test logs if the profile changes.

### 4. F-08 / F-09c — Nginx and production frontend routing

1. Build and start the production frontend container.
2. Request the HTTP endpoint with the configured canonical host and with an untrusted `Host` header; verify the redirect destination.
3. Request the HTTPS frontend and inspect `Content-Security-Policy` on the main page and relevant error/location responses.
4. Verify the production frontend sends API requests to same-origin `/api` and does not use the local development address.

**Pass criteria:** Redirects use configured `PUBLIC_HOST` (while documented localhost behavior remains usable); the expected CSP is present; API calls resolve through `/api` on the same origin.

## Current evidence and remaining work

- Compose resource limits, WebRTC policy flags, CSP/canonical redirect, and the production `/api` setting have been added in code.
- `docker compose config --quiet` passed on the Windows development host. This validates Compose syntax but does not prove runtime enforcement.
- The Docker Desktop Linux engine was unavailable during the last recorded run, so Linux packet capture, POSIX cleanup, `docker inspect` resource verification, and live Nginx response checks have not been recorded.
- The seccomp allowlist has intentionally not been changed. Review it only after Chromium has been tested in the target Linux container.
- Phase 5 remains **open** until all applicable pass criteria above have reproducible evidence.

## Execution record

| Date | Host / image | Checks run | Result and evidence |
| :--- | :--- | :--- | :--- |
| 2026-10-19 | Windows development host; Linux Docker engine unavailable | `docker compose config --quiet` | Passed syntax validation. Runtime checks not run; no Linux result claimed. |

