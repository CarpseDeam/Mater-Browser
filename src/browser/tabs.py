"""Multi-tab management."""
import logging
import time
from typing import Optional

from playwright.sync_api import Browser, BrowserContext

from .page import Page

logger = logging.getLogger(__name__)


class TabManager:
    """Manages browser tabs/contexts."""

    def __init__(self, browser: Browser) -> None:
        """Initialize tab manager.

        Args:
            browser: Playwright Browser instance.
        """
        self._browser = browser
        self._context: Optional[BrowserContext] = None

    @property
    def context(self) -> BrowserContext:
        """Get or create browser context."""
        if not self._context:
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = self._browser.new_context()
        return self._context

    def get_page(self, index: int = 0) -> Page:
        """Get page by index, creating if needed.

        Args:
            index: Page index (0-based).

        Returns:
            Page wrapper instance.
        """
        pages = self.context.pages
        if index < len(pages):
            return Page(pages[index])
        return Page(self.context.new_page())

    def new_page(self) -> Page:
        """Create a new page/tab.

        Returns:
            New Page wrapper instance.
        """
        return Page(self.context.new_page())

    def close_extras(self, keep: int = 1) -> None:
        """Close all but first N tabs.

        Args:
            keep: Number of tabs to keep open.
        """
        pages = self.context.pages
        for page in pages[keep:]:
            try:
                page.close()
            except Exception:
                pass

    def get_all_pages(self) -> list[Page]:
        """Get all open pages/tabs.

        Returns:
            List of Page wrapper instances.
        """
        return [Page(p) for p in self.context.pages]

    def wait_for_new_tab(self, timeout: int = 5000) -> Optional[Page]:
        """Wait for a new tab to open and return it.

        Args:
            timeout: Maximum time to wait in milliseconds.

        Returns:
            New Page wrapper if a new tab opened, None otherwise.
        """
        start = time.time()
        initial_count = len(self.context.pages)

        while (time.time() - start) * 1000 < timeout:
            if len(self.context.pages) > initial_count:
                logger.info("New tab detected")
                return Page(self.context.pages[-1])
            time.sleep(0.1)

        return None

    def get_latest_page(self) -> Page:
        """Get the most recently opened page/tab.

        Returns:
            Most recent Page wrapper instance.
        """
        pages = self.context.pages
        if pages:
            return Page(pages[-1])
        return Page(self.context.new_page())
