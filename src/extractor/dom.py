"""Raw DOM extraction utilities."""
import logging
from typing import Optional

from ..browser.page import Page

logger = logging.getLogger(__name__)


class DOMExtractor:
    """Extracts raw DOM information from pages."""

    def __init__(self, page: Page) -> None:
        """Initialize DOM extractor.

        Args:
            page: Page wrapper instance.
        """
        self._page = page

    def get_text_content(self, selector: str) -> Optional[str]:
        """Get text content of an element.

        Args:
            selector: CSS selector.

        Returns:
            Text content or None if not found.
        """
        try:
            locator = self._page.raw.locator(selector).first
            return locator.text_content()
        except Exception as e:
            logger.debug(f"Failed to get text for {selector}: {e}")
            return None

    def get_attribute(self, selector: str, attribute: str) -> Optional[str]:
        """Get attribute value of an element.

        Args:
            selector: CSS selector.
            attribute: Attribute name.

        Returns:
            Attribute value or None if not found.
        """
        try:
            locator = self._page.raw.locator(selector).first
            return locator.get_attribute(attribute)
        except Exception as e:
            logger.debug(f"Failed to get {attribute} for {selector}: {e}")
            return None

    def exists(self, selector: str) -> bool:
        """Check if an element exists on the page.

        Args:
            selector: CSS selector.

        Returns:
            True if element exists.
        """
        try:
            return self._page.raw.locator(selector).count() > 0
        except Exception:
            return False
