After the latest pull and build, verify the outstanding Linux items in plan/Review Security 14-10-2026.md. First read the report and inspect the actual runtime configuration. Do not modify the code or close findings based on assumptions.
Verify and record evidence for the following:
1. The image, Playwright, and Chromium versions inside the running container match the versions specified by the project.
2. Capture runs as a non-root user and uses the expected Chromium sandbox, seccomp profile, read-only filesystem, capabilities, and network restrictions.
3. SSRF protections, including redirects to loopback or private IPs; WebSocket blocking; and CDP restrictions.
4. Screenshot route behavior for normal, multi-range, and malformed Range headers, confirming that each returns the full file as expected.
5. Capture budgets and behavior when limits are exceeded. Verify the CPU, memory, and PID limits actually in effect. If limits are configured, test them in a separate safe environment.
6. Run the backend tests, Ruff, and mypy in the Linux environment, and record the actual commands and results.
Use a test environment only. Do not run load tests or security tests against production without authorization. If an item cannot be tested, document what is missing and what evidence is still needed. Then update section 7 of the report to reflect the actual results. Do not close any finding whose acceptance criteria have not been met.