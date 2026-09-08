# Local Authentication Security Plan

## Purpose

This document defines the minimum security baseline for adding locally managed username/password authentication to the Web Defacement Monitor. It supplements `codereviewbygptsol.md` and applies when no external identity provider is available.

The recommended initial design uses server-managed sessions in secure cookies. It does not store JWTs, session identifiers, or refresh tokens in browser `localStorage` or `sessionStorage`. The authentication boundary should remain replaceable so the application can migrate to OIDC later without rewriting authorization rules.

## Recommended Architecture

```text
React frontend
    -> POST /auth/login with username and password
FastAPI backend
    -> verify password hash
    -> create a cryptographically random server-side session
Database
    -> store only a hash of the session token
FastAPI backend
    -> return the raw session token in a secure HttpOnly cookie
Browser
    -> automatically send the cookie on subsequent same-origin requests
```

For the first release, accounts should be provisioned by an administrator. Public self-registration should remain disabled. All authenticated users may initially share one `Authenticated User` role, while the data model should allow future `Viewer`, `Operator`, and `Administrator` roles.

## Security Requirements

### 1. Password Storage

- Hash passwords with Argon2id using a maintained password-hashing library.
- Use a unique random salt for every password. The selected library should generate and encode the salt automatically.
- Never store plaintext passwords or reversibly encrypted passwords.
- Do not use general-purpose fast hashes such as MD5, SHA-1, or SHA-256 for password storage.
- Store the algorithm and cost parameters with the encoded password hash so parameters can be upgraded later.
- Rehash a password after a successful login when its stored cost parameters are obsolete.
- Define a minimum password length and permit long passwords and passphrases.
- Do not silently truncate passwords.
- Consider a server-side pepper stored outside the database as defense in depth, but do not treat it as a substitute for Argon2id.

Reference: [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

### 2. Login Responses and Account Enumeration

- Return the same user-facing message for an unknown username, incorrect password, disabled account, or locked account: `Invalid username or password`.
- Keep the response status, response shape, and approximate processing time consistent across failure cases.
- Do not expose whether an account exists through password-reset or account-management endpoints.
- Store detailed internal failure reasons only in protected audit logs.

### 3. Login Rate Limiting

- Apply separate limits per normalized username and per source IP address.
- Both limits must pass before password verification proceeds.
- Use a token-bucket or sliding-window strategy rather than a single fixed window.
- Return HTTP 429 with a generic response when the limit is exceeded.
- Do not reveal which limiter triggered or how many attempts remain.
- Place stricter limits on authentication endpoints than ordinary application endpoints.
- Ensure rate-limit state works across processes if the application is scaled horizontally.

### 4. Temporary Lockout and Progressive Delay

- Track failed login attempts against the account, not only the source IP.
- Apply a short temporary lockout or exponential delay after repeated failures.
- Reset or decay the counter after a successful login and after the observation window expires.
- Set an upper bound on the delay.
- Design the policy so an attacker cannot permanently deny access by intentionally locking another user's account.
- Provide an administrator-controlled recovery path for internal users.

### 5. Account Provisioning

- Keep public registration disabled.
- Allow only an administrator or controlled bootstrap process to create accounts.
- Do not ship a default username/password in source code, container images, documentation, or committed environment files.
- Require a bootstrap credential to be supplied through a protected deployment secret.
- Force bootstrap or temporary passwords to be changed at first login.
- Support account disablement without deleting audit history.
- Enforce unique normalized usernames.

### 6. Session Cookie Security

- Store the session identifier in a cookie with `HttpOnly`, `Secure`, and an appropriate `SameSite` policy.
- Use a host-only cookie where possible and avoid setting a broad `Domain` attribute.
- Use a narrow cookie path appropriate for the application.
- Prefer a cookie name with the `__Host-` prefix when deployment constraints allow it.
- Never place session identifiers in URLs.
- Never store session identifiers, JWTs, or refresh tokens in `localStorage` or `sessionStorage`.
- Require HTTPS outside local development.
- Configure CORS with explicit trusted origins; do not combine credentialed requests with wildcard origins.

Reference: [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)

### 7. CSRF Protection

- Protect every state-changing request when authentication relies on cookies.
- Use a proven synchronizer-token or signed double-submit-cookie implementation.
- Validate the `Origin` header for browser mutation requests as defense in depth.
- Keep `SameSite` enabled, but do not treat it as the only CSRF defense.
- Reject mutation requests with missing or invalid CSRF tokens.
- Do not use GET requests for state-changing operations.

### 8. Logout and Session Revocation

- Generate session tokens with a cryptographically secure random number generator.
- Store only a cryptographic hash of each session token in the database.
- Revoke the database session during logout before expiring the browser cookie.
- Support revoking all sessions for a user after password changes, account disablement, suspected compromise, or administrator action.
- Rotate the session identifier after login and after any privilege change to prevent session fixation.
- Treat a missing or revoked session as unauthenticated.

### 9. Expiration and Idle Timeout

- Enforce both an absolute session lifetime and an idle timeout on the server.
- Do not rely only on the browser cookie expiration time.
- Update `last_seen_at` in a bounded manner to avoid a database write on every request.
- Reject expired sessions even if a stale cookie remains in the browser.
- Define shorter lifetimes for privileged sessions if administrator roles are introduced.
- Require re-authentication for sensitive actions when appropriate.

### 10. Audit Logging

- Record successful and failed login events.
- Record logout, session revocation, password changes, account creation, account disablement, lockout, unlock, and authorization-role changes.
- Include timestamp, user ID when known, normalized event type, outcome, request correlation ID, and appropriate source information.
- Do not log plaintext passwords, raw session tokens, password hashes, CSRF tokens, or full sensitive request bodies.
- Protect audit logs from ordinary application users and define a retention policy.
- Avoid logging untrusted strings without normalization or output encoding.

### 11. MFA Roadmap

- Design the user and authentication models so MFA can be added before production.
- Prefer standards-based TOTP or WebAuthn/passkeys rather than custom verification mechanisms.
- Require MFA for administrator accounts before production deployment.
- Define recovery-code generation, secure storage, one-time use, and regeneration behavior.
- Audit MFA enrollment, removal, success, failure, and recovery events.

## Suggested Data Model

### `users`

- `id`: non-predictable primary identifier.
- `username`: display value.
- `normalized_username`: unique lookup value.
- `password_hash`: encoded Argon2id hash.
- `role`: initially `authenticated_user`; extensible to RBAC roles.
- `is_active`: account enablement flag.
- `must_change_password`: first-login/reset control.
- `failed_login_count`: failed-attempt state.
- `first_failed_login_at`: observation-window state.
- `locked_until`: temporary lockout deadline.
- `password_changed_at`: password lifecycle timestamp.
- `created_at`, `updated_at`: record timestamps.

### `sessions`

- `id`: database identifier.
- `token_hash`: unique hash of the random browser session token.
- `user_id`: owning user.
- `created_at`: issue time.
- `last_seen_at`: server-observed activity time.
- `absolute_expires_at`: maximum lifetime.
- `idle_expires_at`: inactivity deadline.
- `revoked_at`: revocation timestamp.
- `revocation_reason`: normalized reason.
- `created_ip_hash` or privacy-reviewed source metadata, if required.

### `auth_audit_events`

- `id`: event identifier.
- `occurred_at`: event timestamp.
- `event_type`: normalized event name.
- `user_id`: nullable related user.
- `outcome`: success or failure.
- `request_id`: correlation identifier.
- `source_metadata`: privacy-reviewed request context.
- `details`: bounded structured metadata without secrets.

## Suggested API Surface

- `POST /auth/login`: authenticate and create a session.
- `POST /auth/logout`: revoke the current session.
- `GET /auth/me`: return the current authenticated user and role.
- `POST /auth/change-password`: rotate the password and revoke other sessions.
- Administrative account-management endpoints should be added only after authorization checks exist.

Every existing application endpoint except an explicitly public `/health` endpoint should require an authenticated session. The backend, not the frontend, must enforce this requirement.

## Frontend Requirements

- Add a login page and an authenticated application boundary.
- Request `/auth/me` during application initialization.
- Use credentialed same-origin requests or an explicitly configured trusted API origin.
- Never persist authentication secrets in Web Storage.
- Treat HTTP 401 as an unauthenticated state and return to login.
- Treat HTTP 403 as an authenticated but unauthorized state.
- Do not infer authorization from hidden buttons; the backend remains authoritative.
- Do not expose raw backend authentication diagnostics to users.

## Tests Required Before Release

### Password Tests

- New passwords are stored as Argon2id hashes, never plaintext.
- Identical passwords produce different encoded hashes because of unique salts.
- Correct passwords verify and incorrect passwords fail.
- Obsolete cost parameters trigger rehash after successful login.

### Login and Enumeration Tests

- Unknown username, wrong password, disabled account, and locked account produce the same public response.
- Failure paths have comparable response behavior.
- Successful login rotates any existing pre-authentication session identifier.

### Rate-Limit and Lockout Tests

- Per-username limits work across different IP addresses.
- Per-IP limits work across different usernames.
- Temporary lockout expires correctly.
- A successful login resets or decays failure state according to policy.
- Concurrent failed attempts cannot bypass counters.

### Cookie and CSRF Tests

- The session cookie has the required `HttpOnly`, `Secure`, and `SameSite` attributes in production configuration.
- Mutation requests without a valid CSRF token are rejected.
- Requests from an untrusted `Origin` are rejected.
- Authentication credentials never appear in Web Storage or URLs.

### Session Tests

- Logout revokes the database session and expires the cookie.
- Revoked, idle-expired, and absolute-expired sessions are rejected.
- Password changes revoke other sessions.
- Disabling an account invalidates its active sessions.
- Session rotation prevents fixation.

### Audit Tests

- Required authentication and account events are recorded.
- Passwords, raw tokens, hashes, and CSRF secrets never appear in logs.
- Audit access is protected from ordinary users.

## Deployment Requirements

- Supply authentication secrets through a secret manager or protected environment injection, not committed files.
- Use HTTPS and secure cookies in every non-local environment.
- Restrict database and administrative endpoints to the minimum required network scope.
- Back up the user and session database according to the application's recovery policy.
- Define procedures for bootstrap administration, account recovery, key/pepper rotation, incident response, and audit review.
- Document how local authentication will migrate to an OIDC identity provider later.

## Completion Criteria

Local authentication is ready for internal use only when:

- Passwords are protected with Argon2id and verified through a maintained library.
- Login enumeration, brute force, credential stuffing, and lockout abuse have explicit controls and tests.
- Browser credentials use secure HttpOnly cookies and are absent from Web Storage.
- CSRF protection covers all cookie-authenticated mutations.
- Logout, revocation, idle expiration, and absolute expiration are enforced by the server.
- Public registration is disabled and account provisioning is controlled.
- Authentication and authorization-relevant events are audited without recording secrets.
- All existing protected endpoints reject unauthenticated requests.
- A documented plan exists for MFA and eventual migration to OIDC before production.
