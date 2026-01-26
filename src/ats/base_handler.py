"""Base class for ATS handlers."""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from playwright.sync_api import Page, Locator

logger = logging.getLogger(__name__)


class FormPage(Enum):
    """Current state of the application flow."""
    JOB_LISTING = "job_listing"
    LOGIN_REQUIRED = "login_required"
    LOGIN = "login"
    FORM = "form"
    PERSONAL_INFO = "personal_info"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    DOCUMENTS = "documents"
    QUESTIONS = "questions"
    REVIEW = "review"
    CONFIRMATION = "confirmation"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class PageResult:
    """Result from a handler action."""
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
    def detect_page_state(self) -> FormPage:
        """Detect current page state in the application flow."""
        pass

    @abstractmethod
    def fill_current_page(self) -> PageResult:
        """Fill all fields on the current page."""
        pass

    @abstractmethod
    def advance_page(self) -> PageResult:
        """Click next/submit to advance to the next page."""
        pass

    def apply(self) -> PageResult:
        """Main entry point - run the full application flow."""
        max_pages = 15
        for page_num in range(max_pages):
            logger.info(f"{self.ATS_NAME}: Page {page_num + 1}")

            state = self.detect_page_state()
            logger.info(f"{self.ATS_NAME}: Page state: {state.value}")

            if state == FormPage.CONFIRMATION:
                return PageResult(True, state, "Application submitted", False)

            if state == FormPage.LOGIN_REQUIRED:
                return PageResult(False, state, "Login required", False)

            if state == FormPage.ERROR:
                return PageResult(False, state, "Error page detected", False)

            if state == FormPage.JOB_LISTING:
                result = self._click_apply_button()
                if not result.success:
                    return result
                self._wait(2000)
                continue

            if state == FormPage.FORM:
                fill_result = self.fill_current_page()
                if not fill_result.success:
                    logger.warning(
                        f"{self.ATS_NAME}: Fill failed: {fill_result.message}"
                    )

                advance_result = self.advance_page()
                if not advance_result.success:
                    return advance_result
                self._wait(2000)
                continue

            # Unknown state - try to advance anyway
            logger.warning(
                f"{self.ATS_NAME}: Unknown state, attempting to advance"
            )
            advance_result = self.advance_page()
            if not advance_result.success:
                return PageResult(False, state, "Stuck on unknown page", False)
            self._wait(2000)

        return PageResult(
            False, FormPage.UNKNOWN, f"Exceeded max pages ({max_pages})", False
        )

    def _click_apply_button(self) -> PageResult:
        """Click the apply button on job listing page."""
        for selector in self.APPLY_BUTTON_SELECTORS:
            try:
                loc = self._page.locator(selector).first
                if loc.is_visible(timeout=2000):
                    loc.click()
                    logger.info(
                        f"{self.ATS_NAME}: Clicked apply button: {selector}"
                    )
                    return PageResult(
                        True, FormPage.JOB_LISTING, "Clicked apply", True
                    )
            except Exception:
                continue
        return PageResult(
            False, FormPage.JOB_LISTING, "Could not find apply button", False
        )

    def _click_next_button(self) -> PageResult:
        """Click next/continue button."""
        all_selectors = self.NEXT_BUTTON_SELECTORS + self.SUBMIT_BUTTON_SELECTORS
        for selector in all_selectors:
            try:
                loc = self._page.locator(selector).first
                if loc.is_visible(timeout=2000):
                    loc.click()
                    logger.info(
                        f"{self.ATS_NAME}: Clicked next button: {selector}"
                    )
                    return PageResult(True, FormPage.FORM, "Advanced page", True)
            except Exception:
                continue
        return PageResult(
            False, FormPage.FORM, "Could not find next button", False
        )

    def _fill_field(self, selector: str, value: str) -> bool:
        """Fill a single field by selector."""
        try:
            loc = self._page.locator(selector).first
            if not loc.is_visible(timeout=1000):
                return False
            loc.clear()
            loc.fill(value)
            logger.debug(f"{self.ATS_NAME}: Filled {selector}")
            return True
        except Exception as e:
            logger.debug(f"{self.ATS_NAME}: Could not fill {selector}: {e}")
            return False

    def _select_option(self, selector: str, value: str) -> bool:
        """Select dropdown option by visible text."""
        try:
            loc = self._page.locator(selector).first
            if not loc.is_visible(timeout=1000):
                return False
            loc.select_option(label=value)
            logger.debug(f"{self.ATS_NAME}: Selected {value} in {selector}")
            return True
        except Exception as e:
            logger.debug(f"{self.ATS_NAME}: Could not select {selector}: {e}")
            return False

    def _click_checkbox(self, selector: str) -> bool:
        """Click a checkbox if not already checked."""
        try:
            loc = self._page.locator(selector).first
            if not loc.is_visible(timeout=1000):
                return False
            if not loc.is_checked():
                loc.click()
            logger.debug(f"{self.ATS_NAME}: Checked {selector}")
            return True
        except Exception as e:
            logger.debug(f"{self.ATS_NAME}: Could not check {selector}: {e}")
            return False

    def _upload_file(self, selector: str, file_path: str) -> bool:
        """Upload a file to input."""
        try:
            loc = self._page.locator(selector).first
            loc.set_input_files(file_path)
            logger.debug(f"{self.ATS_NAME}: Uploaded file to {selector}")
            return True
        except Exception as e:
            logger.debug(f"{self.ATS_NAME}: Could not upload to {selector}: {e}")
            return False

    def _wait(self, ms: int) -> None:
        """Wait for specified milliseconds."""
        self._page.wait_for_timeout(ms)

    def _has_element(self, selector: str) -> bool:
        """Check if element exists and is visible."""
        try:
            return self._page.locator(selector).first.is_visible(timeout=1000)
        except Exception:
            return False

    def _get_text(self, selector: str) -> Optional[str]:
        """Get text content of element."""
        try:
            loc = self._page.locator(selector).first
            if loc.is_visible(timeout=1000):
                return loc.text_content()
        except Exception:
            pass
        return None
