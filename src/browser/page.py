"""Page wrapper with utility methods."""
import logging

from playwright.sync_api import Page as PlaywrightPage

logger = logging.getLogger(__name__)


class Page:
    """Wrapper around Playwright Page with common utilities."""

    def __init__(self, page: PlaywrightPage) -> None:
        """Initialize page wrapper.

        Args:
            page: Playwright Page instance.
        """
        self._page = page

    @property
    def url(self) -> str:
        """Get current page URL."""
        return self._page.url

    @property
    def raw(self) -> PlaywrightPage:
        """Access underlying Playwright page for advanced operations."""
        return self._page

    def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:
        """Navigate to URL.

        Args:
            url: Target URL.
            wait_until: Wait condition (domcontentloaded, load, networkidle).
        """
        logger.info(f"Navigating to: {url}")
        self._page.goto(url, wait_until=wait_until)

    def wait(self, ms: int) -> None:
        """Wait for specified milliseconds.

        Args:
            ms: Milliseconds to wait.
        """
        self._page.wait_for_timeout(ms)

    def content(self) -> str:
        """Get page HTML content."""
        return self._page.content()

    def screenshot(self, path: str) -> None:
        """Take a screenshot.

        Args:
            path: File path to save screenshot.
        """
        self._page.screenshot(path=path)
