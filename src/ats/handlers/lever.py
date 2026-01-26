"""Lever ATS handler."""
import logging

from ..base_handler import BaseATSHandler, FormPage, PageResult

logger = logging.getLogger(__name__)


class LeverHandler(BaseATSHandler):
    """Handler for Lever ATS applications."""

    ATS_NAME = "lever"

    APPLY_BUTTON_SELECTORS = [
        'a.postings-btn:has-text("Apply")',
        'button:has-text("Apply for this job")',
        ".apply-button",
    ]

    NEXT_BUTTON_SELECTORS = [
        'button[type="submit"]',
        'button:has-text("Submit application")',
        'button:has-text("Submit")',
    ]

    SUBMIT_BUTTON_SELECTORS = NEXT_BUTTON_SELECTORS

    FIELD_SELECTORS = {
        "name": [
            'input[name="name"]',
            "#name",
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
            'input[type="file"][name="resume"]',
            '.resume-upload input[type="file"]',
        ],
        "linkedin": [
            'input[name="urls[LinkedIn]"]',
            'input[placeholder*="LinkedIn"]',
        ],
        "github": [
            'input[name="urls[GitHub]"]',
            'input[placeholder*="GitHub"]',
        ],
        "portfolio": [
            'input[name="urls[Portfolio]"]',
            'input[name="urls[Other]"]',
        ],
        "current_company": [
            'input[name="org"]',
            "#current-company",
        ],
    }

    def detect_page_type(self) -> FormPage:
        """Detect current Lever page type."""
        if self._is_visible('text="Thank you"', timeout=500):
            return FormPage.CONFIRMATION
        if self._is_visible(".application-form", timeout=500):
            return FormPage.PERSONAL_INFO
        if self._is_visible(".postings-btn", timeout=500):
            return FormPage.JOB_LISTING
        return FormPage.UNKNOWN

    def fill_current_page(self) -> PageResult:
        """Fill Lever application."""
        page_type = self.detect_page_type()

        if page_type == FormPage.CONFIRMATION:
            return PageResult(True, page_type, "Application submitted", False)

        if page_type == FormPage.JOB_LISTING:
            if self.click_apply():
                self._wait(1500)
                page_type = FormPage.PERSONAL_INFO

        return self._fill_application_form()

    def _fill_application_form(self) -> PageResult:
        """Fill the Lever application form."""
        filled = self._fill_basic_fields()
        self._fill_url_fields()
        self._fill_company_field()
        self._upload_resume()
        self._handle_custom_questions()

        if self.click_submit():
            self._wait(3000)
            if self.detect_page_type() == FormPage.CONFIRMATION:
                return PageResult(
                    True, FormPage.PERSONAL_INFO, "Application submitted", False
                )
            return PageResult(
                True, FormPage.PERSONAL_INFO, f"Filled {filled} fields", True
            )

        return PageResult(False, FormPage.PERSONAL_INFO, "Could not submit", False)

    def _fill_basic_fields(self) -> int:
        """Fill basic required fields."""
        filled = 0
        full_name = f"{self._profile.get('first_name', '')} {self._profile.get('last_name', '')}".strip()
        if self._fill_field(self.FIELD_SELECTORS["name"], full_name):
            filled += 1

        if self._fill_field(
            self.FIELD_SELECTORS["email"], self._profile.get("email", "")
        ):
            filled += 1
        if self._fill_field(
            self.FIELD_SELECTORS["phone"], self._profile.get("phone", "")
        ):
            filled += 1
        return filled

    def _fill_url_fields(self) -> None:
        """Fill URL fields."""
        self._fill_field(
            self.FIELD_SELECTORS["linkedin"], self._profile.get("linkedin_url", "")
        )
        self._fill_field(
            self.FIELD_SELECTORS["github"], self._profile.get("github_url", "")
        )
        self._fill_field(
            self.FIELD_SELECTORS["portfolio"], self._profile.get("portfolio_url", "")
        )

    def _fill_company_field(self) -> None:
        """Fill current company field."""
        self._fill_field(
            self.FIELD_SELECTORS["current_company"],
            self._profile.get("current_company", ""),
        )

    def _upload_resume(self) -> None:
        """Upload resume if path provided."""
        if self._resume_path:
            self._upload_file(self.FIELD_SELECTORS["resume"], self._resume_path)
            self._wait(1500)

    def _handle_custom_questions(self) -> None:
        """Handle Lever custom questions."""
        self._check_all_checkboxes()
        self._select_option(['select[name*="authorized"]'], "Yes")
        self._select_option(['select[name*="sponsor"]'], "No")

    def _check_all_checkboxes(self) -> None:
        """Check all visible checkboxes."""
        try:
            checkboxes = self._page.locator('input[type="checkbox"]:visible').all()
            for cb in checkboxes:
                if not cb.is_checked():
                    cb.check()
        except Exception:
            pass
