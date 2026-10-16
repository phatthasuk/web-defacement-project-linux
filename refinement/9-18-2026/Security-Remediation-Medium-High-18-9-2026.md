# Refinement Record: Security Remediation (Medium & High Vulnerabilities)

**Date:** September 18, 2026  
**Status:** **Implementation and automated verification complete (54 security-regression tests passed)**  
**Scope:** Reverse Proxy Rate Limiting (DoS prevention), Clickjacking Protection, Nginx Header Inheritance, and Browser Capture `file://` Scheme Isolation.

---

## 1. Background & Objectives

Following the multi-dimensional security review of the codebase on September 17–18, 2026, four specific vulnerabilities were identified and remediated:
1. **[High]** SlowAPI Rate Limiter on `/auth/login` evaluating the Nginx container IP instead of the client's real IP, leading to potential Denial of Service (DoS) across all users.
2. **[Medium]** Missing Clickjacking protection headers (`X-Frame-Options` and Content-Security-Policy `frame-ancestors`).
3. **[Medium]** Nginx header inheritance failure in child `location` blocks (`location ~* \.(?:css|js...)$` and `location /`) causing parent security headers (`HSTS`, `X-Content-Type-Options`, `Referrer-Policy`) to be dropped when `add_header Cache-Control` was invoked.
4. **[Medium]** Overly permissive `file://` scheme handling in `guard_navigation` inside Playwright capture service, which could allow compromised remote targets to query local container files via `<iframe>` or subresources.

---

## 2. Implemented Changes

### 2.1 [High] Reverse Proxy Client IP Resolution & Rate Limiter DoS Prevention
- **Files Modified:**
  - `backend/app/api/routes/auth.py`
  - `backend/Dockerfile`
  - `docker-compose.yml`
  - `docker-compose.dev.yml`
  - `frontend/nginx.conf`
  - `backend/tests/test_auth.py`
- **Details:**
  - **Trust Boundary:** Nginx is the production public entry point and replaces `X-Forwarded-For` and `X-Real-IP` with its observed client address. It never appends a caller-supplied value.
  - **Uvicorn Configuration:** Production enables proxy headers but accepts them only from the fixed frontend container IP (`172.30.0.2`). Compose reserves `172.30.0.2` for the frontend and `172.30.0.3` for the unexposed backend on a dedicated `172.30.0.0/24` network. Development explicitly disables proxy-header processing because it exposes the backend directly.
  - **Application Logic:** `get_client_ip(request)` uses only `request.client`, which Uvicorn has already rewritten after enforcing the proxy trust policy. It never directly interprets client-controlled forwarding headers.
  - **Automated Tests:** Added tests proving forwarded-header spoofing cannot evade the five-request login limit (`429` on the sixth request), while separate peer IPs retain independent limits.

### 2.2 [Medium] Clickjacking Protection & Nginx Security Header Inheritance
- **Files Modified:**
  - `frontend/nginx.conf`
- **Details:**
  - Added `add_header X-Frame-Options "SAMEORIGIN" always;` and `add_header Content-Security-Policy "frame-ancestors 'self';" always;`.
  - Fixed Nginx's configuration inheritance quirk where defining `add_header` within child blocks resets all server-level headers. Explicitly declared the full security header suite (`Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy`) across all location contexts:
    - Main TLS `server` block (port 8443)
    - Static asset caching block (`location ~* \.(?:css|js|jpg|jpeg|gif|png|ico|svg|woff|woff2|ttf|eot)$`)
    - SPA routing fallback block (`location /`)

### 2.3 [Medium] Playwright `file://` Scheme Isolation for Remote Targets
- **Files Modified:**
  - `backend/app/services/capture/capture.py`
  - `backend/tests/test_capture.py`
- **Details:**
  - Separated in-memory browser schemes (`data:`, `blob:`, `about:`) from local filesystem schemes.
  - Restricted `file://` navigation in `guard_navigation`: It is now only permitted if the root capture target itself was loaded via `file://` (offline unit test fixtures). Any remote target (`http://` or `https://`) attempting to load `file://` subresources or iframes is logged with a security warning and immediately aborted via `await route.abort()`.
  - Added automated unit test `test_capture_snapshot_blocks_file_subresource_from_remote_target` in `test_capture.py` verifying that local file subresources from remote origins are blocked while safe `data:` URIs remain allowed.

---

## 3. Verification & Test Matrix

| Test Suite | Command | Result |
|---|---|---|
| Full Security Suite | `.venv\\Scripts\\python.exe -m pytest tests/test_auth.py tests/test_ssrf_guard.py tests/test_ssrf_proxy.py tests/test_api_routes.py -q` | **54 passed, 1 dependency deprecation warning** |
| Capture & Subresource Tests | `.venv\\Scripts\\python.exe -m pytest tests/test_capture.py -k "file_subresource or sandbox or iframes" -q` | **4 passed, 12 deselected, 1 dependency deprecation warning** |
| Lint | `.venv\\Scripts\\python.exe -m ruff check app/api/routes/auth.py tests/test_auth.py` | **Passed** |
| Compose validation | `docker compose -f docker-compose.yml config --quiet` and development equivalent | **Passed** |
| Production DB Integrity | `backend/data/app.db` | **Not opened or modified by this remediation** |

---

## 4. Preservation & Compliance

- Existing monitoring targets, check histories, snapshots, and baseline approval workflows remain 100% intact.
- Backward compatibility for offline test fixtures using `FIXTURE_PATH.as_uri()` is fully preserved.
- No breaking changes introduced to frontend build or backend dependencies.
- Container-level Nginx-to-Uvicorn verification remains pending because Docker Desktop was not running on the verification host.
