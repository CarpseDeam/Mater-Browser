"""Phenom ATS handler (used by companies like GitHub, etc.)."""
import logging

from ..base_handler import BaseATSHandler, FormPage, PageResult

logger = logging.getLogger(__name__)


class PhenomHandler(BaseATSHandler):
    """Handler for Phenom ATS applications."""

    ATS_NAME = "phenom"

    APPLY_BUTTON_SELECTORS = [
        "#link-apply",
        '[data-ph-at-id="apply-link"]',
        'a:has-text("Apply")',
        'button:has-text("Apply")',
    ]

    NEXT_BUTTON_SELECTORS = [
        "#next",
        '[data-ph-at-id="next-button"]',
        'button:has-text("Next")',
        'button:has-text("Continue")',
    ]

    SUBMIT_BUTTON_SELECTORS = [
        "#submit",
        '[data-ph-at-id="submit-button"]',
        'button:has-text("Submit")',
    ]

    FIELD_SELECTORS = {
        "email": ["#email", 'input[name="email"]', 'input[type="email"]'],
        "first_name": ["#firstName", 'input[name="firstName"]'],
        "last_name": ["#lastName", 'input[name="lastName"]'],
        "phone": ["#phone", 'input[name="phone"]', 'input[type="tel"]'],
        "city": ["#city", 'input[name="city"]'],
        "resume": ['input[type="file"]'],
    }

    def detect_page_type(self) -> FormPage:
        """Detect current Phenom page type."""
        url = self._page.url.lower()

        if "/confirmation" in url or self._is_visible('text="Thank you"'):
            return FormPage.CONFIRMATION
        if "/login" in url or self._is_visible('input[type="password"]'):
            return FormPage.LOGIN
        if self._is_visible("#link-apply"):
            return FormPage.JOB_LISTING
        if self._is_visible("form"):
            return FormPage.PERSONAL_INFO
        return FormPage.UNKNOWN

    def fill_current_page(self) -> PageResult:
        """Fill current Phenom page."""
        page_type = self.detect_page_type()

        if page_type == FormPage.CONFIRMATION:
            return PageResult(True, page_type, "Application submitted", False)
        if page_type == FormPage.LOGIN:
            return PageResult(False, page_type, "Login required", False)
        if page_type == FormPage.JOB_LISTING:
            return self._handle_job_listing()

        return self._fill_form()

    def _handle_job_listing(self) -> PageResult:
        """Click Apply on job listing page."""
        if self.click_apply():
            self._wait(2000)
            return PageResult(True, FormPage.JOB_LISTING, "Clicked Apply", True)
        return PageResult(False, FormPage.JOB_LISTING, "No Apply button", False)

    def _fill_form(self) -> PageResult:
        """Fill Phenom application form."""
        filled = self._fill_basic_fields()
        self._upload_resume()
        self._check_all_checkboxes()

        if self.click_next():
            return PageResult(
                True, FormPage.PERSONAL_INFO, f"Filled {filled}, advanced", True
            )
        if self.click_submit():
            self._wait(3000)
            return PageResult(True, FormPage.PERSONAL_INFO, "Submitted", False)

        return PageResult(False, FormPage.PERSONAL_INFO, "Could not advance", False)

    def _fill_basic_fields(self) -> int:
        """Fill basic contact fields."""
        filled = 0
        fields = [
            ("email", "email"),
            ("first_name", "first_name"),
            ("last_name", "last_name"),
            ("phone", "phone"),
            ("city", "city"),
        ]
        for selector_key, profile_key in fields:
            if self._fill_field(
                self.FIELD_SELECTORS[selector_key], self._profile.get(profile_key, "")
            ):
                filled += 1
        return filled

    def _upload_resume(self) -> None:
        """Upload resume if path provided."""
        if self._resume_path:
            self._upload_file(self.FIELD_SELECTORS["resume"], self._resume_path)

    def _check_all_checkboxes(self) -> None:
        """Check all visible checkboxes."""
        try:
            for cb in self._page.locator('input[type="checkbox"]:visible').all():
                if not cb.is_checked():
                    cb.check()
        except Exception:
            pass
