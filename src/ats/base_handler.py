"""Base class for ATS handlers."""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from playwright.sync_api import Page

logger = logging.getLogger(__name__)


class FormPage(Enum):
    """Types of pages in an application flow."""
    JOB_LISTING = "job_listing"
    LOGIN = "login"
    PERSONAL_INFO = "personal_info"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    QUESTIONS = "questions"
    DOCUMENTS = "documents"
    REVIEW = "review"
    CONFIRMATION = "confirmation"
    UNKNOWN = "unknown"


@dataclass
class PageResult:
    """Result of processing a page."""
    success: bool
    page_type: FormPage
    message: str
    needs_next_page: bool = True


class BaseATSHandler(ABC):
    """Abstract base class for ATS-specific handlers."""

    ATS_NAME: str = "base"

    APPLY_BUTTON_SELECTORS: list[str] = []
    NEXT_BUTTON_SELECTORS: list[str] = []
    SUBMIT_BUTTON_SELECTORS: list[str] = []

    def __init__(
        self, page: Page, profile: dict, resume_path: Optional[str] = None
    ) -> None:
        self._page = page
        self._profile = profile
        self._resume_path = resume_path

    @abstractmethod
    def detect_page_type(self) -> FormPage:
        """Detect what type of page we're on."""
        pass

    @abstractmethod
    def fill_current_page(self) -> PageResult:
        """Fill all fields on the current page."""
        pass

    def click_apply(self) -> bool:
        """Click the Apply button."""
        return self._click_first_visible(self.APPLY_BUTTON_SELECTORS)

    def click_next(self) -> bool:
        """Click the Next/Continue button."""
        return self._click_first_visible(self.NEXT_BUTTON_SELECTORS)

    def click_submit(self) -> bool:
        """Click the final Submit button."""
        return self._click_first_visible(self.SUBMIT_BUTTON_SELECTORS)

    def _click_first_visible(self, selectors: list[str]) -> bool:
        """Click the first visible element from a list of selectors."""
        for selector in selectors:
            try:
                loc = self._page.locator(selector).first
                if loc.is_visible(timeout=2000):
                    loc.click()
                    logger.info(f"{self.ATS_NAME}: Clicked {selector}")
                    self._page.wait_for_timeout(1000)
                    return True
            except Exception:
                continue
        return False

    def _fill_field(self, selectors: list[str], value: str) -> bool:
        """Fill a field using the first matching selector."""
        if not value:
            return False
        for selector in selectors:
            try:
                loc = self._page.locator(selector).first
                if loc.is_visible(timeout=1000):
                    loc.clear()
                    loc.fill(value)
                    logger.info(f"{self.ATS_NAME}: Filled {selector}")
                    return True
            except Exception:
                continue
        return False

    def _select_option(self, selectors: list[str], value: str) -> bool:
        """Select an option from a dropdown."""
        for selector in selectors:
            try:
                loc = self._page.locator(selector).first
                if loc.is_visible(timeout=1000):
                    loc.select_option(label=value)
                    logger.info(f"{self.ATS_NAME}: Selected {value} in {selector}")
                    return True
            except Exception:
                continue
        return False

    def _upload_file(self, selectors: list[str], file_path: str) -> bool:
        """Upload a file to the first matching file input."""
        for selector in selectors:
            try:
                loc = self._page.locator(selector).first
                if loc.count() > 0:
                    loc.set_input_files(file_path)
                    logger.info(f"{self.ATS_NAME}: Uploaded to {selector}")
                    return True
            except Exception:
                continue
        return False

    def _check_checkbox(self, selectors: list[str]) -> bool:
        """Check a checkbox."""
        for selector in selectors:
            try:
                loc = self._page.locator(selector).first
                if loc.is_visible(timeout=1000):
                    if not loc.is_checked():
                        loc.check()
                    logger.info(f"{self.ATS_NAME}: Checked {selector}")
                    return True
            except Exception:
                continue
        return False

    def _is_visible(self, selector: str, timeout: int = 1000) -> bool:
        """Check if an element is visible."""
        try:
            return self._page.locator(selector).first.is_visible(timeout=timeout)
        except Exception:
            return False

    def _wait(self, ms: int = 1000) -> None:
        """Wait for specified milliseconds."""
        self._page.wait_for_timeout(ms)
