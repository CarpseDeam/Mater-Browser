"""Lever ATS handler."""
import logging
from typing import Optional

from playwright.sync_api import Page

from ..base_handler import BaseATSHandler, PageResult, FormPage

logger = logging.getLogger(__name__)


class LeverHandler(BaseATSHandler):
    """Handler for Lever ATS."""

    ATS_NAME = "lever"

    APPLY_BUTTON_SELECTORS = [
        ".posting-btn-submit",
        "a[href*='/apply']",
        "button:has-text('Apply')",
    ]

    NEXT_BUTTON_SELECTORS = [
        "button[type='submit']",
        "button:has-text('Submit application')",
        ".submit-application",
    ]

    SUBMIT_BUTTON_SELECTORS = [
        "button[type='submit']",
        "button:has-text('Submit')",
    ]

    def __init__(
        self, page: Page, profile: dict, resume_path: Optional[str] = None
    ) -> None:
        super().__init__(page, profile, resume_path)

    def detect_page_state(self) -> FormPage:
        """Detect Lever page state."""
        url = self._page.url.lower()

        if self._is_confirmation_page(url):
            return FormPage.CONFIRMATION

        if self._is_form_page(url):
            return FormPage.FORM

        if self._is_job_listing_page():
            return FormPage.JOB_LISTING

        return FormPage.UNKNOWN

    def _is_confirmation_page(self, url: str) -> bool:
        """Check if current page is confirmation."""
        if "/thanks" in url or "confirmation" in url:
            return True
        return self._has_element(".thank-you")

    def _is_form_page(self, url: str) -> bool:
        """Check if current page is a form."""
        if "/apply" in url:
            return True
        return self._has_element(".application-form")

    def _is_job_listing_page(self) -> bool:
        """Check if current page is job listing."""
        return self._has_element(".posting-btn-submit")

    def fill_current_page(self) -> PageResult:
        """Fill Lever form."""
        filled_count = 0

        filled_count += self._fill_name_field()
        filled_count += self._fill_contact_fields()
        filled_count += self._fill_url_fields()
        self._upload_resume()

        logger.info(f"{self.ATS_NAME}: Filled {filled_count} fields")
        return PageResult(
            True, FormPage.FORM, f"Filled {filled_count} fields", True
        )
    def _fill_name_field(self) -> int:
        """Fill the name field (Lever uses single name field)."""
        first = self._profile.get("first_name", "")
        last = self._profile.get("last_name", "")
        name = f"{first} {last}".strip()

        if self._fill_field("input[name='name']", name):
            return 1
        return 0

    def _fill_contact_fields(self) -> int:
        """Fill email and phone fields."""
        filled = 0
        if self._fill_field("input[name='email']", self._profile.get("email", "")):
            filled += 1
        if self._fill_field("input[name='phone']", self._profile.get("phone", "")):
            filled += 1
        return filled

    def _fill_url_fields(self) -> int:
        """Fill URL fields."""
        filled = 0
        linkedin = self._profile.get("linkedin_url", "")
        github = self._profile.get("github_url", "")
        portfolio = self._profile.get("portfolio_url", "")

        if linkedin and self._fill_field("input[name*='LinkedIn' i]", linkedin):
            filled += 1
        if github and self._fill_field("input[name*='GitHub' i]", github):
            filled += 1
        if portfolio and self._fill_field("input[name*='Portfolio' i]", portfolio):
            filled += 1

        return filled

    def _upload_resume(self) -> None:
        """Upload resume if path provided."""
        if self._resume_path:
            self._upload_file("input[type='file'][name='resume']", self._resume_path)

    def advance_page(self) -> PageResult:
        """Submit application."""
        return self._click_next_button()
