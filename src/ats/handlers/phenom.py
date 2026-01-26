"""Phenom/Taleo ATS handler."""
import logging
from typing import Optional

from playwright.sync_api import Page

from ..base_handler import BaseATSHandler, HandlerResult, PageState
from ..field_mapper import FieldMapper

logger = logging.getLogger(__name__)


class PhenomHandler(BaseATSHandler):
    """Handler for Phenom (modern Taleo) ATS."""

    ATS_NAME = "phenom"

    APPLY_BUTTON_SELECTORS = [
        "#link-apply",
        "[data-ph-id*='apply']",
        "a:has-text('Apply')",
        "button:has-text('Apply')",
    ]

    NEXT_BUTTON_SELECTORS = [
        "#next",
        "#btn-next",
        "button:has-text('Next')",
        "button:has-text('Continue')",
        "[data-ph-id*='next']",
    ]

    SUBMIT_BUTTON_SELECTORS = [
        "#submit",
        "button:has-text('Submit')",
        "[data-ph-id*='submit']",
    ]

    def __init__(
        self, page: Page, profile: dict, resume_path: Optional[str] = None
    ) -> None:
        super().__init__(page, profile, resume_path)
        self._mapper = FieldMapper(profile)

    def detect_page_state(self) -> PageState:
        """Detect Phenom page state."""
        url = self._page.url.lower()

        if self._is_confirmation_page(url):
            return PageState.CONFIRMATION

        if self._is_login_page(url):
            return PageState.LOGIN_REQUIRED

        if self._is_form_page(url):
            return PageState.FORM

        if self._is_job_listing_page():
            return PageState.JOB_LISTING

        return PageState.UNKNOWN

    def _is_confirmation_page(self, url: str) -> bool:
        """Check if current page is confirmation."""
        if "/confirmation" in url or "/thank" in url:
            return True
        return self._has_element(".application-success")

    def _is_login_page(self, url: str) -> bool:
        """Check if login is required."""
        if "/login" in url:
            return True
        return self._has_element("input[type='password']")

    def _is_form_page(self, url: str) -> bool:
        """Check if current page is a form."""
        if "/apply" in url:
            return True
        return (
            self._has_element("#next") or
            self._has_element("#submit")
        )

    def _is_job_listing_page(self) -> bool:
        """Check if current page is job listing."""
        return self._has_element("#link-apply")

    def fill_current_page(self) -> HandlerResult:
        """Fill Phenom form fields."""
        filled_count = 0

        filled_count += self._fill_standard_fields()
        self._select_country()
        self._fill_linkedin_field()
        self._upload_resume()
        self._handle_checkboxes()

        logger.info(f"{self.ATS_NAME}: Filled {filled_count} fields")
        return HandlerResult(
            True, f"Filled {filled_count} fields", PageState.FORM
        )

    def _fill_standard_fields(self) -> int:
        """Fill standard form fields."""
        filled = 0
        field_mappings = [
            ("#firstName", self._profile.get("first_name", "")),
            ("#lastName", self._profile.get("last_name", "")),
            ("#email", self._profile.get("email", "")),
            ("#phoneNumber", self._profile.get("phone", "")),
            ("#city", self._get_city()),
            ("#state", self._get_state()),
            ("#zipCode", self._get_zip()),
        ]

        for selector, value in field_mappings:
            if value and self._fill_field(selector, value):
                filled += 1

        return filled

    def _select_country(self) -> None:
        """Select country dropdown."""
        self._select_option("#country", "United States")

    def _fill_linkedin_field(self) -> None:
        """Fill LinkedIn URL field."""
        linkedin = self._profile.get("linkedin_url", "")
        if linkedin:
            self._fill_field("[id*='linkedin' i]", linkedin)
            self._fill_field("[name*='linkedin' i]", linkedin)

    def _upload_resume(self) -> None:
        """Upload resume if path provided."""
        if self._resume_path:
            self._upload_file("input[type='file']", self._resume_path)

    def _handle_checkboxes(self) -> None:
        """Handle privacy and consent checkboxes."""
        self._click_checkbox("#privacyPolicy")
        self._click_checkbox("input[type='checkbox'][required]")

    def _get_city(self) -> str:
        """Extract city from location."""
        location = self._profile.get("location", "")
        if "," in location:
            return location.split(",")[0].strip()
        return location

    def _get_state(self) -> str:
        """Extract state from location."""
        location = self._profile.get("location", "")
        if "," in location:
            parts = location.split(",")[-1].strip().split()
            if parts:
                return parts[0]
        return ""

    def _get_zip(self) -> str:
        """Extract zip from location."""
        location = self._profile.get("location", "")
        if "," in location:
            parts = location.split(",")[-1].strip().split()
            if len(parts) > 1:
                return parts[1]
        return ""

    def advance_page(self) -> HandlerResult:
        """Click next/submit."""
        return self._click_next_button()
