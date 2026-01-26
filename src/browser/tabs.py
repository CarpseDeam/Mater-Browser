"""Multi-tab management."""
import logging
import time
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page as PlaywrightPage

from .page import Page

logger = logging.getLogger(__name__)


class TabManager:
    """Manages browser tabs/contexts with popup interception."""

    def __init__(self, browser: Browser) -> None:
        """Initialize tab manager.

        Args:
            browser: Playwright Browser instance.
        """
        self._browser = browser
        self._context: Optional[BrowserContext] = None
        self._popup_url: Optional[str] = None
        self._popup_handler_installed: bool = False

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
            page = Page(pages[index])
            self._install_popup_handler(pages[index])
            return page
        new_page = self.context.new_page()
        self._install_popup_handler(new_page)
        return Page(new_page)

    def _install_popup_handler(self, page: PlaywrightPage) -> None:
        """Install popup handler to capture new tab URLs without focus stealing."""
        if self._popup_handler_installed:
            return

        def on_popup(popup: PlaywrightPage) -> None:
            try:
                popup.wait_for_load_state("domcontentloaded", timeout=5000)
                self._popup_url = popup.url
                logger.info(f"Captured popup URL: {self._popup_url}")
                popup.close()
            except Exception as e:
                logger.debug(f"Popup handling error: {e}")
                try:
                    self._popup_url = popup.url
                    popup.close()
                except Exception:
                    pass

        page.on("popup", on_popup)
        self._popup_handler_installed = True

    def get_captured_popup_url(self) -> Optional[str]:
        """Get and clear the captured popup URL.

        Returns:
            The URL that was opened in a popup, or None if no popup was captured.
        """
        url = self._popup_url
        self._popup_url = None
        return url

    def clear_popup_url(self) -> None:
        """Clear any captured popup URL."""
        self._popup_url = None

    def new_page(self) -> Page:
        """Create a new page/tab.

        Returns:
            New Page wrapper instance.
        """
        new_page = self.context.new_page()
        self._install_popup_handler(new_page)
        return Page(new_page)

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
