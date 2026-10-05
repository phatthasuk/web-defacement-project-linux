"""Preserve overlays as capture evidence.

Page-controlled labels and vendor CSS selectors cannot establish trust. Clicking
any consent or close control can execute attacker code that removes evidence.
Automatic dismissal is therefore disabled, including for legacy configurations
with DISMISS_OVERLAYS enabled. Keep the result API for existing capture metadata.
"""

from dataclasses import dataclass

from playwright.async_api import Page

__all__ = ["OverlayDismissal", "dismiss_overlays"]


@dataclass(frozen=True)
class OverlayDismissal:
    """Compatibility metadata; capture no longer dismisses overlays."""

    cookie_dismissed: bool = False
    promo_closed: bool = False

    @property
    def changed_page(self) -> bool:
        return self.cookie_dismissed or self.promo_closed


async def dismiss_overlays(page: Page) -> OverlayDismissal:
    """Leave the page untouched so all captured artifacts retain evidence."""
    return OverlayDismissal()
