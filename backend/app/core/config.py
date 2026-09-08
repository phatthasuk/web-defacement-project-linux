from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Web Defacement Monitor"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Session cookie behaviour is centralised here so login, logout, and tests
    # stay consistent. Production must run with SESSION_COOKIE_SECURE=True
    # (enforced at startup in app.main).
    SESSION_COOKIE_NAME: str = "session_id"
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    SESSION_COOKIE_PATH: str = "/"
    SESSION_ABSOLUTE_LIFETIME_SECONDS: int = 14 * 24 * 60 * 60  # 14 days
    SESSION_IDLE_TIMEOUT_SECONDS: int = 24 * 60 * 60  # 1 day
    # How often last_seen_at / idle deadline is refreshed, to bound DB writes.
    SESSION_ACTIVITY_REFRESH_SECONDS: int = 60

    # Login brute-force controls.
    LOGIN_MAX_FAILED_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_SECONDS: int = 15 * 60  # 15 minutes
    LOGIN_FAILURE_WINDOW_SECONDS: int = 15 * 60
    LOGIN_RATE_LIMIT: str = "5/minute"

    CSRF_HEADER_NAME: str = "X-CSRF-Token"

    DATABASE_URL: str = "sqlite:///./data/app.db"

    DATA_DIR: str = "./data"

    # Scheduler settings (Stage 1.1)
    SCHEDULER_ENABLED: bool = True
    CHECK_INTERVAL_SECONDS: int = 3600  # 1 hour
    CHECK_JITTER_MAX_SECONDS: int = 180  # 0-3 minutes random jitter
    SCHEDULER_POLL_INTERVAL_SECONDS: int = 15
    STAGING_CLEANUP_MAX_AGE_SECONDS: int = 1800  # 30 minutes

    MAX_CONCURRENT_CHECKS: int = 2
    PER_DOMAIN_CONCURRENCY: int = 1
    PAGE_TIMEOUT_SECONDS: int = 25
    CHECK_TIMEOUT_SECONDS: int = 90
    REDIRECT_LIMIT: int = 5
    MAX_ARTIFACT_SIZE_MB: int = 10

    # A fixed viewport keeps captures comparable between checks; a viewport that
    # follows the window would move layout and register as a visual change.
    VIEWPORT_WIDTH: int = 1440
    VIEWPORT_HEIGHT: int = 900

    # Chromium's own sandbox is the last line of defence when rendering a page
    # that may already be compromised, so it stays ON by default. Only disable
    # it where the container cannot support it (e.g. running as root), and then
    # compensate with container isolation — see plan/archive/codereviewbygptsol.md
    # Finding 7.
    BROWSER_DISABLE_SANDBOX: bool = False

    # WebSocket connections are not covered by page.route(), so they could
    # otherwise reach an internal address without passing the SSRF guard
    # (Finding 6). Capture never needs them.
    BLOCK_WEBSOCKETS: bool = True

    # Page stabilisation before capture. Freezing animations/carousels and
    # forcing lazy images to load is what stops an unchanged page from
    # producing a visual diff on every check.
    PAGE_STABILIZE_ENABLED: bool = True
    PAGE_NETWORK_QUIET_MS: int = 1200
    PAGE_NETWORK_MAX_WAIT_MS: int = 15000
    PAGE_VISIBLE_CONTENT_TIMEOUT_MS: int = 5000
    PAGE_EXTRA_WAIT_MS: int = 1000
    DISMISS_OVERLAYS: bool = True

    # A target may hold several approved baselines at once. A page with content
    # that legitimately rotates (hero carousels, promo panels) has more than one
    # correct appearance, and comparing against only the newest one reports a
    # change every time a different variant is served. A check is compared
    # against every baseline and judged by the closest match.
    MAX_BASELINES_PER_TARGET: int = 20

    # A check is only flagged as Changed when a diff score exceeds its threshold.
    # Small non-zero defaults absorb minor rendering/text noise (timestamps,
    # antialiasing) so live targets do not report a change on every check.
    TEXT_CHANGE_THRESHOLD: float = 0.02
    VISUAL_CHANGE_THRESHOLD: float = 0.01
    # Zero tolerance by design: a single new external script or iframe is worth
    # reporting no matter how small a share of the page it represents. Expected
    # third parties belong in a target's allowed_domains, not in this threshold.
    STRUCTURE_CHANGE_THRESHOLD: float = 0.0

    ALLOWED_SCHEMES: str = "http,https"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_schemes_list(self) -> list[str]:
        return [scheme.strip() for scheme in self.ALLOWED_SCHEMES.split(",") if scheme.strip()]

    @property
    def data_dir_path(self) -> Path:
        return Path(self.DATA_DIR)


@lru_cache
def get_settings() -> Settings:
    return Settings()
