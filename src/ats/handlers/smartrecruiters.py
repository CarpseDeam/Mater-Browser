"""SmartRecruiters ATS handler."""
import logging
from typing import Optional

from ..base_handler import BaseATSHandler, FormPage, PageResult

logger = logging.getLogger(__name__)


class SmartRecruitersHandler(BaseATSHandler):
    """Handler for SmartRecruiters ATS applications."""

    ATS_NAME = "smartrecruiters"

    APPLY_BUTTON_SELECTORS = [
        'button:has-text("Apply")',
        'a:has-text("Apply Now")',
        '[data-test="apply-button"]',
        ".apply-btn",
    ]

    NEXT_BUTTON_SELECTORS = [
        'button[type="submit"]',
        'button:has-text("Next")',
        'button:has-text("Continue")',
        '[data-test="next-button"]',
    ]

    SUBMIT_BUTTON_SELECTORS = [
        'button:has-text("Submit")',
        'button:has-text("Submit Application")',
        '[data-test="submit-button"]',
    ]

    FIELD_SELECTORS = {
        "first_name": [
            'input[name="firstName"]',
            "#firstName",
            'input[autocomplete="given-name"]',
        ],
        "last_name": [
            'input[name="lastName"]',
            "#lastName",
            'input[autocomplete="family-name"]',
        ],
        "email": [
            'input[name="email"]',
            "#email",
            'input[type="email"]',
        ],
        "phone": [
            'input[name="phone"]',
            "#phone",
            'input[type="tel"]',
        ],
        "resume": [
            'input[type="file"]',
            '[data-test="resume-upload"]',
        ],
        "linkedin": [
            'input[name*="linkedin" i]',
            'input[placeholder*="LinkedIn"]',
        ],
    }

    PAGE_INDICATORS = {
        FormPage.JOB_LISTING: [
            '[data-test="job-details"]',
            ".job-details",
        ],
        FormPage.PERSONAL_INFO: [
            '[data-test="application-form"]',
            'form[class*="application"]',
        ],
        FormPage.CONFIRMATION: [
            '[data-test="confirmation"]',
            'text="Thank you"',
            'text="Application submitted"',
        ],
    }

    def _is_visible(self, selector: str, timeout: int = 500) -> bool:
        """Check if element is visible."""
        try:
            return self._page.locator(selector).first.is_visible(timeout=timeout)
        except Exception:
            return False

    def detect_page_state(self) -> FormPage:
        """Detect current SmartRecruiters page state."""
        for selector in self.PAGE_INDICATORS[FormPage.CONFIRMATION]:
            if self._is_visible(selector, timeout=500):
                return FormPage.CONFIRMATION

        for selector in self.PAGE_INDICATORS[FormPage.PERSONAL_INFO]:
            if self._is_visible(selector, timeout=500):
                return FormPage.PERSONAL_INFO

        for selector in self.PAGE_INDICATORS[FormPage.JOB_LISTING]:
            if self._is_visible(selector, timeout=500):
                return FormPage.JOB_LISTING

        return FormPage.UNKNOWN

    def fill_current_page(self) -> PageResult:
        """Fill SmartRecruiters application."""
        page_type = self.detect_page_state()

        if page_type == FormPage.CONFIRMATION:
            return PageResult(True, page_type, "Application submitted", False)

        if page_type == FormPage.JOB_LISTING:
            return PageResult(True, page_type, "On job listing page", True)

        return self._fill_application_form()

    def advance_page(self) -> PageResult:
        """Click next/submit to advance to the next page."""
        page_type = self.detect_page_state()
        
        if page_type == FormPage.JOB_LISTING:
            if self.click_apply():
                return PageResult(True, FormPage.PERSONAL_INFO, "Clicked apply", True)
            return PageResult(False, FormPage.JOB_LISTING, "Could not find apply button", False)

        if self.click_submit():
            return PageResult(True, FormPage.CONFIRMATION, "Clicked submit", True)
        if self.click_next():
            return PageResult(True, FormPage.PERSONAL_INFO, "Advanced to next page", True)
        return PageResult(False, FormPage.PERSONAL_INFO, "Could not advance", False)

    def click_apply(self) -> bool:
        """Click the apply button."""
        for selector in self.APPLY_BUTTON_SELECTORS:
            try:
                loc = self._page.locator(selector).first
                if loc.is_visible(timeout=500):
                    loc.click()
                    return True
            except Exception:
                continue
        return False

    def click_next(self) -> bool:
        """Click the next button."""
        for selector in self.NEXT_BUTTON_SELECTORS:
            try:
                loc = self._page.locator(selector).first
                if loc.is_visible(timeout=500):
                    loc.click()
                    return True
            except Exception:
                continue
        return False

    def click_submit(self) -> bool:
        """Click the submit button."""
        for selector in self.SUBMIT_BUTTON_SELECTORS:
            try:
                loc = self._page.locator(selector).first
                if loc.is_visible(timeout=500):
                    loc.click()
                    return True
            except Exception:
                continue
        return False

    def _fill_application_form(self) -> PageResult:
        """Fill the application form."""
        filled = self._fill_basic_fields()
        self._fill_optional_fields()
        self._upload_resume()
        self._check_all_checkboxes()

        return PageResult(
            True, FormPage.PERSONAL_INFO, f"Filled {filled} fields", True
        )

    def _fill_basic_fields(self) -> int:
        """Fill basic contact fields."""
        filled = 0
        fields = [
            ("first_name", "first_name"),
            ("last_name", "last_name"),
            ("email", "email"),
            ("phone", "phone"),
        ]
        for selector_key, profile_key in fields:
            if self._fill_field(
                self.FIELD_SELECTORS[selector_key], self._profile.get(profile_key, "")
            ):
                filled += 1
        return filled

    def _fill_optional_fields(self) -> None:
        """Fill optional fields."""
        self._fill_field(
            self.FIELD_SELECTORS["linkedin"], self._profile.get("linkedin_url", "")
        )

    def _upload_resume(self) -> None:
        """Upload resume if path provided."""
        if self._resume_path:
            self._upload_file(self.FIELD_SELECTORS["resume"], self._resume_path)
            self._wait(1500)

    def _check_all_checkboxes(self) -> None:
        """Check all visible checkboxes."""
        try:
            checkboxes = self._page.locator('input[type="checkbox"]:visible').all()
            for cb in checkboxes:
                if not cb.is_checked():
                    cb.check()
        except Exception:
            pass

    def _fill_field(self, selectors: list, value: str) -> bool:
        """Fill a field using multiple selector options."""
        for selector in selectors:
            if super()._fill_field(selector, value):
                return True
        return False

    def _upload_file(self, selectors: list, file_path: str) -> bool:
        """Upload a file using multiple selector options."""
        for selector in selectors:
            if super()._upload_file(selector, file_path):
                return True
        return False
