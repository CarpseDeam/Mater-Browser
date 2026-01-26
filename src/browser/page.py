"""Page wrapper with utility methods."""
import logging

from playwright.sync_api import Page as PlaywrightPage

from ..agent.models import MEDIUM_WAIT_MS, PAGE_LOAD_TIMEOUT_MS, MAX_NAVIGATION_RETRIES

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

    def goto(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        max_retries: int = MAX_NAVIGATION_RETRIES,
    ) -> bool:
        """Navigate to URL with retry logic.

        Returns True if navigation succeeded, False if all retries failed.
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"Navigating to: {url} (attempt {attempt + 1})")
                self._page.goto(url, wait_until=wait_until, timeout=PAGE_LOAD_TIMEOUT_MS)
                return True
            except Exception as e:
                if not self._handle_navigation_error(e, url, attempt, max_retries):
                    raise
        return False

    def _handle_navigation_error(
        self, error: Exception, url: str, attempt: int, max_retries: int
    ) -> bool:
        """Handle navigation error. Returns True if error was recoverable."""
        error_msg = str(error).lower()
        if "err_aborted" in error_msg or "aborted" in error_msg:
            logger.warning(f"Navigation aborted (attempt {attempt + 1}): {error}")
            self.wait(MEDIUM_WAIT_MS)
            if url.split("?")[0] in self._page.url:
                logger.info("Navigation succeeded despite abort")
                return True
        if attempt < max_retries - 1:
            logger.warning(f"Navigation failed (attempt {attempt + 1}): {error}")
            self.wait(MEDIUM_WAIT_MS)
            return True
        logger.error(f"Navigation failed after {max_retries} attempts: {error}")
        return False

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
