"""Greenhouse ATS handler."""
import logging
from typing import Optional

from playwright.sync_api import Page

from ..base_handler import BaseATSHandler, FormPage, PageResult
from ..field_mapper import FieldMapper

logger = logging.getLogger(__name__)


class GreenhouseHandler(BaseATSHandler):
    """Handler for Greenhouse ATS."""

    ATS_NAME = "greenhouse"

    APPLY_BUTTON_SELECTORS = [
        "#apply_button",
        "[data-testid='apply-button']",
        "a[href*='/apply']",
        "button:has-text('Apply')",
        ".btn-apply",
    ]

    NEXT_BUTTON_SELECTORS = [
        "#submit_app",
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Submit')",
        "button:has-text('Next')",
        "button:has-text('Continue')",
    ]

    SUBMIT_BUTTON_SELECTORS = [
        "#submit_app",
        "button[type='submit']:has-text('Submit')",
        "input[value='Submit Application']",
    ]

    FIELD_SELECTORS = {
        "first_name": "#first_name",
        "last_name": "#last_name",
        "email": "#email",
        "phone": "#phone",
        "resume": "#resume",
        "linkedin_url": "#job_application_answers_attributes_0_text_value",
        "location": "#job_application_location",
    }

    def __init__(
        self, page: Page, profile: dict, resume_path: Optional[str] = None
    ) -> None:
        super().__init__(page, profile, resume_path)
        self._mapper = FieldMapper(profile)

    def detect_page_state(self) -> FormPage:
        """Detect current page state."""
        url = self._page.url.lower()

        if self._is_confirmation_page(url):
            return FormPage.CONFIRMATION

        if self._has_element("input[type='password']"):
            return FormPage.LOGIN_REQUIRED

        if self._is_form_page():
            return FormPage.FORM

        if self._is_job_listing_page():
            return FormPage.JOB_LISTING

        return FormPage.UNKNOWN

    def _is_confirmation_page(self, url: str) -> bool:
        """Check if current page is confirmation."""
        if "/confirmation" in url or "/thank" in url:
            return True
        if self._has_element(".flash-success"):
            return True
        if self._has_element("[class*='thank-you']"):
            return True
        return False

    def _is_form_page(self) -> bool:
        """Check if current page is a form."""
        return (
            self._has_element("#application_form") or
            self._has_element("#first_name")
        )

    def _is_job_listing_page(self) -> bool:
        """Check if current page is job listing."""
        return (
            self._has_element("#apply_button") or
            self._has_element("[data-testid='apply-button']")
        )

    def fill_current_page(self) -> PageResult:
        """Fill all fields on the current Greenhouse page."""
        filled_count = 0

        filled_count += self._fill_basic_fields()
        filled_count += self._fill_location_field()
        filled_count += self._fill_linkedin_field()
        self._upload_resume()
        self._handle_checkboxes()

        logger.info(f"{self.ATS_NAME}: Filled {filled_count} fields")
        return PageResult(
            True, FormPage.FORM, f"Filled {filled_count} fields", True
        )

    def _fill_basic_fields(self) -> int:
        """Fill basic contact fields."""
        filled = 0
        if self._fill_field("#first_name", self._profile.get("first_name", "")):
            filled += 1
        if self._fill_field("#last_name", self._profile.get("last_name", "")):
            filled += 1
        if self._fill_field("#email", self._profile.get("email", "")):
            filled += 1
        if self._fill_field("#phone", self._profile.get("phone", "")):
            filled += 1
        return filled

    def _fill_location_field(self) -> int:
        """Fill location field."""
        location = self._profile.get("location", "")
        if self._fill_field("#job_application_location", location):
            return 1
        return 0

    def _fill_linkedin_field(self) -> int:
        """Fill LinkedIn URL field."""
        linkedin = self._profile.get("linkedin_url", "")
        if not linkedin:
            return 0

        linkedin_selectors = [
            "input[name*='linkedin' i]",
            "input[placeholder*='linkedin' i]",
            "[id*='linkedin' i]",
        ]
        for sel in linkedin_selectors:
            if self._fill_field(sel, linkedin):
                return 1
        return 0

    def _upload_resume(self) -> None:
        """Upload resume if path provided."""
        if not self._resume_path:
            return

        resume_selectors = [
            "#resume",
            "input[type='file'][name*='resume' i]",
            "input[type='file']",
        ]
        for sel in resume_selectors:
            if self._upload_file(sel, self._resume_path):
                break

    def _handle_checkboxes(self) -> None:
        """Check any required checkboxes."""
        self._click_checkbox("input[type='checkbox'][required]")

    def advance_page(self) -> PageResult:
        """Click submit button."""
        return self._click_next_button()
