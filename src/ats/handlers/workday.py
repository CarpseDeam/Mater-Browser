"""Workday ATS handler."""
import logging
from typing import Optional

from playwright.sync_api import Page

from ..base_handler import BaseATSHandler, FormPage, PageResult
from ..field_mapper import FieldMapper

logger = logging.getLogger(__name__)


class WorkdayHandler(BaseATSHandler):
    """Handler for Workday ATS."""

    ATS_NAME = "workday"

    APPLY_BUTTON_SELECTORS = [
        "[data-automation-id='jobPostingApplyButton']",
        "button[data-uxi-element-id='Apply']",
        "a[data-automation-id='applyButton']",
        "button:has-text('Apply')",
    ]

    NEXT_BUTTON_SELECTORS = [
        "[data-automation-id='bottom-navigation-next-button']",
        "[data-automation-id='nextButton']",
        "button:has-text('Next')",
        "button:has-text('Continue')",
    ]

    SUBMIT_BUTTON_SELECTORS = [
        "[data-automation-id='bottom-navigation-next-button']",
        "button:has-text('Submit')",
        "[data-automation-id='submitButton']",
    ]

    def __init__(
        self, page: Page, profile: dict, resume_path: Optional[str] = None
    ) -> None:
        super().__init__(page, profile, resume_path)
        self._mapper = FieldMapper(profile)

    def detect_page_state(self) -> FormPage:
        """Detect current page state in Workday."""
        url = self._page.url.lower()

        if self._is_confirmation_page(url):
            return FormPage.CONFIRMATION

        if self._is_login_page(url):
            return FormPage.LOGIN_REQUIRED

        if self._is_form_page():
            return FormPage.FORM

        if self._is_job_listing_page():
            return FormPage.JOB_LISTING

        return FormPage.UNKNOWN

    def _is_confirmation_page(self, url: str) -> bool:
        """Check if current page is confirmation."""
        if "/thankYou" in url or "/confirmation" in url:
            return True
        return self._has_element("[data-automation-id='thankYouMessage']")

    def _is_login_page(self, url: str) -> bool:
        """Check if login is required."""
        if "/login" in url:
            return True
        return self._has_element("[data-automation-id='signInLink']")

    def _is_form_page(self) -> bool:
        """Check if current page is a form."""
        return (
            self._has_element("[data-automation-id='formField']") or
            self._has_element("[data-automation-id='bottom-navigation-next-button']")
        )

    def _is_job_listing_page(self) -> bool:
        """Check if current page is job listing."""
        return self._has_element("[data-automation-id='jobPostingApplyButton']")

    def fill_current_page(self) -> PageResult:
        """Fill all fields on current Workday page."""
        filled_count = 0

        filled_count += self._fill_name_fields()
        filled_count += self._fill_contact_fields()
        filled_count += self._fill_location_fields()
        self._select_country()
        self._select_state()
        self._upload_workday_resume()
        self._handle_workday_questions()

        logger.info(f"{self.ATS_NAME}: Filled {filled_count} fields")
        return PageResult(
            True, FormPage.FORM, f"Filled {filled_count} fields", True
        )

    def _fill_name_fields(self) -> int:
        """Fill first and last name fields."""
        filled = 0
        first_name = self._profile.get("first_name", "")
        last_name = self._profile.get("last_name", "")

        selectors = [
            "[data-automation-id='firstName'] input",
            "input[data-automation-id='firstName']",
        ]
        for sel in selectors:
            if self._fill_field(sel, first_name):
                filled += 1
                break

        selectors = [
            "[data-automation-id='lastName'] input",
            "input[data-automation-id='lastName']",
        ]
        for sel in selectors:
            if self._fill_field(sel, last_name):
                filled += 1
                break

        return filled

    def _fill_contact_fields(self) -> int:
        """Fill email and phone fields."""
        filled = 0
        email = self._profile.get("email", "")
        phone = self._profile.get("phone", "")

        selectors = [
            "[data-automation-id='email'] input",
            "input[data-automation-id='email']",
        ]
        for sel in selectors:
            if self._fill_field(sel, email):
                filled += 1
                break

        selectors = [
            "[data-automation-id='phone'] input",
            "input[data-automation-id='phone']",
        ]
        for sel in selectors:
            if self._fill_field(sel, phone):
                filled += 1
                break

        return filled

    def _fill_location_fields(self) -> int:
        """Fill city and postal code from location."""
        filled = 0
        city = self._get_city()
        zip_code = self._get_zip()

        if city:
            sel = "[data-automation-id='addressSection_city'] input"
            if self._fill_field(sel, city):
                filled += 1

        if zip_code:
            sel = "[data-automation-id='addressSection_postalCode'] input"
            if self._fill_field(sel, zip_code):
                filled += 1

        return filled

    def _select_country(self) -> None:
        """Select country in Workday dropdown."""
        self._select_workday_dropdown("country", "United States")

    def _select_state(self) -> None:
        """Select state in Workday dropdown."""
        state = self._get_state()
        if state:
            self._select_workday_dropdown("state", state)

    def _select_workday_dropdown(self, field_id: str, value: str) -> bool:
        """Handle Workday's custom dropdown components."""
        try:
            dropdown = self._page.locator(
                f"[data-automation-id='{field_id}']"
            ).first
            if not dropdown.is_visible(timeout=1000):
                return False

            dropdown.click()
            self._wait(500)

            option = self._page.locator(
                f"[data-automation-id*='{value}']"
            ).first
            if option.is_visible(timeout=1000):
                option.click()
                return True

            option = self._page.locator(f"li:has-text('{value}')").first
            if option.is_visible(timeout=1000):
                option.click()
                return True
        except Exception as e:
            logger.debug(f"Workday dropdown {field_id} failed: {e}")
        return False

    def _upload_workday_resume(self) -> bool:
        """Upload resume to Workday."""
        if not self._resume_path:
            return False

        selectors = [
            "[data-automation-id='resumeUploadButton'] input[type='file']",
            "input[data-automation-id='fileUpload']",
            "[data-automation-id='file-upload-input-ref'] input[type='file']",
        ]
        for sel in selectors:
            if self._upload_file(sel, self._resume_path):
                return True
        return False

    def _handle_workday_questions(self) -> None:
        """Handle common Workday questions."""
        auth_selectors = [
            "[data-automation-id*='workAuthorization'] input[value='Yes']",
            "label:has-text('authorized to work')",
        ]
        for sel in auth_selectors:
            self._click_checkbox(sel)

        sponsor_selectors = [
            "[data-automation-id*='sponsorship'] input[value='No']",
        ]
        for sel in sponsor_selectors:
            self._click_checkbox(sel)

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

    def advance_page(self) -> PageResult:
        """Click next button in Workday."""
        return self._click_next_button()
