# Local Authentication Implementation Review

## Review Status

**Decision: Request changes before merge or deployment.**

The local username/password authentication implementation follows the intended high-level architecture, but it is not yet safe or complete enough for production or trusted internal use. Several security controls described in `local-authentication-security-plan.md` are missing, and the current automated quality gates do not all pass.

This review is based on the current implementation in the `backend` and `frontend` folders. No application source code was modified during this review.

## What Has Been Implemented

- Argon2 password hashing through Passlib and `argon2-cffi`.
- `User` and `Session` SQLAlchemy models.
- `POST /auth/login`, `POST /auth/logout`, and `GET /auth/me` routes.
- Authentication dependencies on the existing targets, checks, snapshots, review, and configuration routers.
- An unauthenticated `/health` endpoint.
- A bootstrap script for creating the first local user.
- Credentialed frontend API requests.
- A frontend authentication context, login page, navigation logout control, and protected routes.

These are appropriate foundational changes, but they require the corrections below.

---

## Blocking Findings

### 1. Logout Does Not Revoke the Server-Side Session

**Severity:** P1 / High

#### Problem

The logout route clears the browser cookie but does not delete or revoke the corresponding session record in the database. A copied or stolen session token therefore remains valid until its 14-day expiration even after the legitimate user logs out.

This contradicts the stated server-managed session design and the proposed verification step that logout should revoke the session.

#### Evidence

- `backend/app/api/routes/auth.py`, lines 54-61.

#### Required Fix

- Read the current session token from the authentication cookie.
- Hash it using the same session-token hashing function used during login.
- Locate the session record and revoke or delete it before clearing the cookie.
- Use identical cookie name, path, domain, `Secure`, and `SameSite` configuration when setting and deleting the cookie.
- Support revoking every active session for a user after a password change, account disablement, suspected compromise, or administrator action.

#### Tests

- Logout makes the old cookie unusable immediately.
- Replaying a logged-out token returns HTTP 401.
- Logout is idempotent.
- Cookie deletion uses the same cookie scope as cookie creation.

---

### 2. Raw Session Tokens Are Stored in the Database

**Severity:** P1 / High

#### Problem

The UUID stored as `Session.id` is also sent to the browser as the session cookie. Anyone who obtains read access to the database can directly reuse every active session.

#### Evidence

- `backend/app/models/session.py`, lines 7-12.
- `backend/app/api/routes/auth.py`, lines 29-38 and 44-50.

#### Required Fix

- Generate a high-entropy opaque token with a cryptographically secure random number generator, for example `secrets.token_urlsafe(32)`.
- Send the raw token only to the browser.
- Store only a SHA-256 hash of the random token in the database.
- Look up sessions by token hash.
- Rotate the token after login and after any privilege change.
- Never write raw session tokens to logs, errors, audit records, or URLs.

SHA-256 is appropriate for hashing a high-entropy random session token. It is not appropriate for password hashing; passwords must continue to use Argon2id.

#### Tests

- The raw browser token is not present in the database.
- The correct token resolves to its stored hash.
- A modified token returns HTTP 401.
- Session tokens are not exposed in logs.

---

### 3. Cookie-Authenticated Mutations Have No CSRF Protection

**Severity:** P1 / High

#### Problem

The browser automatically attaches the authentication cookie, but state-changing endpoints do not require a CSRF token or validate the request origin. `SameSite=Lax` is useful defense in depth but should not be the only CSRF control.

Affected operations include target creation and deactivation, check triggering, baseline approval, acknowledgement, login, and logout.

#### Required Fix

- Add a proven synchronizer-token or signed double-submit-cookie CSRF implementation.
- Validate the `Origin` header against explicit trusted origins for browser mutation requests.
- Require a valid CSRF token on every cookie-authenticated mutation.
- Keep `SameSite` enabled, but do not treat it as a complete replacement for CSRF validation.
- Do not use GET requests for state-changing operations.

#### Tests

- A mutation without a CSRF token is rejected.
- An invalid token is rejected.
- An untrusted `Origin` is rejected.
- A valid same-origin request with the correct token succeeds.

---

### 4. The Session Cookie Is Hard-Coded as Insecure

**Severity:** P1 / High outside local development

#### Problem

The login and logout routes hard-code `secure=False`. If this configuration is deployed unchanged, the browser may transmit the session cookie over unencrypted HTTP.

#### Evidence

- `backend/app/api/routes/auth.py`, lines 40-50 and line 60.

#### Required Fix

Centralize cookie behavior in application settings, for example:

```text
ENVIRONMENT=development
SESSION_COOKIE_NAME=session_id
SESSION_COOKIE_SECURE=false
SESSION_COOKIE_SAMESITE=lax
SESSION_COOKIE_PATH=/
SESSION_ABSOLUTE_LIFETIME_SECONDS=...
SESSION_IDLE_TIMEOUT_SECONDS=...
```

Required policy:

- Local development over `http://localhost`: `Secure=False` is permitted.
- Staging and production: `Secure=True` is mandatory.
- Application startup must fail if a production environment is configured with `Secure=False`.
- Do not automatically infer whether to disable `Secure` from the incoming request scheme; reverse-proxy configuration can make that decision unreliable.
- Use one shared cookie-settings helper for login, logout, tests, and future session rotation.
- Prefer a host-only cookie and the `__Host-` prefix in HTTPS deployments when its requirements can be satisfied.

#### Tests

- Development configuration produces the intended local cookie.
- Production configuration sets `HttpOnly`, `Secure`, `SameSite`, and the expected path.
- Production startup rejects insecure cookie configuration.

---

### 5. Login Responses Permit Account Enumeration

**Severity:** P1 / High

#### Problem

An incorrect password returns `Incorrect username or password`, while an inactive account returns `User account is inactive`. This reveals whether a username exists and its state. An unknown username also skips Argon2 verification, which can create a timing difference.

#### Evidence

- `backend/app/api/routes/auth.py`, lines 17-27.

#### Required Fix

- Return the same public message for unknown, incorrect-password, inactive, and locked accounts: `Invalid username or password`.
- Keep the status code and response schema identical across these failures.
- Perform a dummy Argon2 verification when no matching user exists to reduce timing differences.
- Keep detailed failure reasons only in protected audit logs.

#### Tests

- Unknown, wrong-password, inactive, and locked users receive the same public response.
- Failure paths have comparable response behavior.
- Internal logs preserve a normalized failure reason without exposing secrets.

---

### 6. There Is No Login Rate Limiting or Lockout Policy

**Severity:** P1 / High

#### Problem

The login route currently allows unlimited password attempts. This leaves the application exposed to brute force, credential stuffing, and password spraying.

#### Required Fix

- Apply independent rate limits per normalized username and per source IP.
- Require both limiters to pass before password verification.
- Use a token-bucket or sliding-window design.
- Add temporary account lockout or bounded exponential delay after repeated failures.
- Reset or decay failure state according to a documented policy after successful login or expiration of the observation window.
- Return a generic HTTP 429 response without disclosing which limiter triggered.
- Use shared rate-limit state if the backend can run in multiple processes or instances.

#### Tests

- A distributed attack across IPs triggers the username limit.
- Multiple usernames from one IP trigger the IP limit.
- Temporary lockout expires correctly.
- Concurrent attempts cannot bypass counters.
- Successful login resets or decays failure state as designed.

---

### 7. The Bootstrap Script Exposes the Password Through Process Arguments

**Severity:** P1 / High

#### Problem

The initial-user script accepts the password as a positional command-line argument. The password can appear in shell history, process listings, CI output, and operational logs.

The script is named `create_admin`, but it creates the `authenticated-user` role, which is misleading.

#### Evidence

- `backend/scripts/create_admin.py`, lines 8-31.

#### Required Fix

- Read passwords interactively with `getpass.getpass()` and require confirmation.
- Support protected standard input or deployment-secret injection for automation.
- Validate the password policy.
- Return a non-zero process exit code on every failure.
- Rename the command to `create_user` or create the actual administrator role implied by the current command name.
- Never ship a default credential in source code, images, documentation, or committed environment files.

#### Tests

- The password is not accepted as a positional argument.
- Password mismatch and weak-password failures return non-zero exit codes.
- Duplicate usernames return a non-zero exit code.
- No password value is printed.

---

## Important Correctness and Hardening Findings

### 8. The Session Model Does Not Support Idle Timeout or Revocation

**Severity:** P2 / Medium to high

The current model contains only an ID, user ID, and expiration timestamp. It should include at least:

- `token_hash` with a unique index.
- `user_id` with a database foreign key.
- `created_at`.
- `last_seen_at`.
- `absolute_expires_at`.
- `idle_expires_at`.
- `revoked_at`.
- `revocation_reason`.

The server must enforce absolute expiration, idle expiration, revocation, and active-user state. Expired and revoked sessions should be removed by scheduled cleanup rather than only when a stale cookie is presented.

Timezone handling must be explicit. Avoid assigning UTC with `replace(tzinfo=...)` unless the stored value is guaranteed to be a naive UTC timestamp.

### 9. Authentication Input Is Not Sufficiently Constrained

**Severity:** P2 / Medium

`LoginRequest` should:

- Forbid unknown fields.
- Define username minimum and maximum lengths.
- Define a bounded password request length without silently truncating it.
- Normalize usernames consistently, including whitespace and case policy.
- Use a unique `normalized_username` column for lookup and uniqueness.

### 10. React Query Data Is Not Cleared During Logout

**Severity:** P2 / High privacy risk on shared browsers

The frontend sets `user` to `null` but leaves cached targets, snapshots, checks, and configuration in the global React Query client. A later user on the same browser may receive data cached for the previous identity.

#### Evidence

- `frontend/src/hooks/useAuth.tsx`, lines 38-45.

#### Required Fix

- Call `queryClient.clear()` after logout and whenever the authenticated identity changes.
- Avoid rendering stale protected content while authentication is being re-established.
- Clear sensitive application state after receiving HTTP 401.

### 11. Authentication Initialization Treats Every Error as Logged Out

**Severity:** P2 / Medium

`/auth/me` failures are all converted to `user = null`. A network failure or HTTP 500 therefore looks like an expired login and may create a misleading redirect loop.

Required behavior:

- HTTP 401: unauthenticated.
- HTTP 403: authenticated but unauthorized.
- Network failure or HTTP 5xx: service error with retry behavior.

### 12. Credential Inclusion Can Be Overridden by Callers

**Severity:** P2 / Medium

`apiFetch` currently places `credentials: 'include'` before `...options`, so a caller can override it. If credentials must always be included, spread caller options first and set `credentials` afterward.

#### Evidence

- `frontend/src/api/client.ts`, lines 28-31.

### 13. Database Schema Evolution Has No Migration Strategy

**Severity:** P2 / Medium

`Base.metadata.create_all()` can create missing tables but cannot reliably evolve authentication tables, constraints, and indexes. Add Alembic migrations for users, sessions, normalized usernames, foreign keys, indexes, revocation fields, and future RBAC changes.

---

## Current Quality-Gate Results

The following commands were run against the current implementation:

### Backend

- Pytest: **11 failed, 38 passed**.
- Mypy: passed for 41 source files.
- Ruff: failed with 25 findings.

The 11 backend test failures occur because existing API tests do not authenticate and now receive HTTP 401. The test suite must gain authenticated fixtures without globally bypassing authentication behavior.

### Frontend

- Vitest: **23 passed across 7 test files**.
- TypeScript type check: failed.
- ESLint: failed with 2 errors and 1 warning.

The TypeScript failure is caused by imports from `lucide-react` while that dependency is not declared in `frontend/package.json`.

Additional frontend issues include an unused caught error and an explicit `any` in the login page.

Passing frontend tests do not validate the new authentication flow because there are no dedicated authentication tests yet.

---

## Required Test Plan

### Backend Authentication Tests

Create a dedicated `backend/tests/test_auth.py` covering:

- Passwords are stored as Argon2id hashes, never plaintext.
- Identical passwords produce different encoded hashes because of unique salts.
- Unknown, wrong-password, inactive, and locked users receive the same public response.
- Username and IP rate limits operate independently.
- Temporary lockout and progressive delay work as specified.
- Production and development cookie attributes are correct.
- Invalid CSRF tokens and untrusted origins are rejected.
- Successful login rotates the session token.
- The database contains only a hash of the raw session token.
- Logout revokes the session immediately.
- Revoked, idle-expired, and absolute-expired sessions return HTTP 401.
- Password changes and account disablement revoke active sessions.
- Protected endpoints reject unauthenticated requests.
- Authenticated clients can execute the existing API tests.
- Secrets never appear in logs or audit records.

Do not solve the existing test failures by globally overriding `get_current_user` in every API test. Provide an authenticated-client fixture for ordinary protected-route tests and retain explicit unauthenticated tests that prove HTTP 401 behavior.

### Frontend Authentication Tests

Add tests covering:

- Initial authentication loading state.
- HTTP 401 redirects to login.
- Network and HTTP 5xx errors show a service error rather than a login redirect.
- Successful and failed login.
- Authenticated navigation.
- Logout revokes the server session and clears React Query state.
- Identity changes do not reuse another user's cached protected data.
- HTTP 403 renders an unauthorized state.
- Authentication credentials are not stored in Web Storage.

---

## Recommended Fix Order

1. Hash session tokens and implement true logout/revocation.
2. Add CSRF and trusted-origin enforcement.
3. Centralize secure cookie configuration and fail closed in production.
4. Remove account-enumeration differences and add dummy password verification.
5. Add username/IP rate limiting, temporary lockout, and authentication audit events.
6. Expand the session and user models, then add Alembic migrations.
7. Secure the bootstrap-user workflow.
8. Correct frontend authentication error handling and clear protected query caches.
9. Add dedicated backend and frontend authentication tests.
10. Resolve missing dependencies, Ruff, ESLint, type-check, and regression-test failures.

## Merge Criteria

The implementation should not be merged as complete until:

- Logout invalidates the server-side session.
- Raw session tokens are absent from the database and logs.
- CSRF validation protects every cookie-authenticated mutation.
- Production cookie configuration cannot run with `Secure=False`.
- Login enumeration and automated guessing have explicit controls.
- Bootstrap credentials cannot leak through command-line arguments.
- Absolute expiration, idle expiration, revocation, and cleanup are enforced.
- Protected query data is cleared across logout and identity changes.
- Database migrations exist for all authentication schema changes.
- Dedicated authentication tests cover success, failure, attack, and expiry scenarios.
- Pytest, Vitest, Ruff, Mypy, ESLint, and TypeScript type checking all pass.

## Related Document

See `plan/local-authentication-security-plan.md` for the complete local-authentication security baseline and future MFA/OIDC migration requirements.
