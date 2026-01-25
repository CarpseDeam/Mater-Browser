"""Chrome CDP connection management."""
import json
import logging
import time
import urllib.request
from typing import Optional

from playwright.sync_api import Browser, Playwright, sync_playwright

logger = logging.getLogger(__name__)


class BrowserConnection:
    """Manages CDP connection to Chrome with retry logic."""

    def __init__(
        self,
        cdp_port: int = 9333,
        max_retries: int = 5,
        retry_delay: float = 2.0,
    ) -> None:
        """Initialize browser connection settings.

        Args:
            cdp_port: Chrome DevTools Protocol port.
            max_retries: Maximum connection attempts.
            retry_delay: Base delay between retries in seconds.
        """
        self.cdp_port = cdp_port
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    @property
    def browser(self) -> Browser:
        """Get the connected browser instance.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._browser:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._browser

    def _check_cdp_endpoint(self) -> bool:
        """Verify CDP endpoint is responding."""
        try:
            url = f"http://127.0.0.1:{self.cdp_port}/json/version"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                logger.debug(f"CDP ready: {data.get('Browser', 'unknown')}")
                return True
        except Exception as e:
            logger.debug(f"CDP not ready: {e}")
            return False

    def connect(self) -> bool:
        """Connect to Chrome with exponential backoff retry.

        Returns:
            True if connection successful, False otherwise.
        """
        for attempt in range(self.max_retries):
            wait_time = min(self.retry_delay * (2**attempt), 30)

            if not self._check_cdp_endpoint():
                logger.info(
                    f"Attempt {attempt + 1}/{self.max_retries}: "
                    f"CDP not ready, waiting {wait_time:.1f}s"
                )
                time.sleep(wait_time)
                continue

            try:
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{self.cdp_port}"
                )
                logger.info("Connected to Chrome successfully")
                return True
            except Exception as e:
                logger.warning(f"Connection failed: {e}")
                self._cleanup()
                time.sleep(wait_time)

        logger.error("Failed to connect after all retries")
        return False

    def _cleanup(self) -> None:
        """Clean up playwright resources."""
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._playwright = None
        self._browser = None

    def disconnect(self) -> None:
        """Close the browser connection."""
        logger.info("Disconnecting from Chrome")
        self._cleanup()
