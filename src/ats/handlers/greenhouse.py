"""Greenhouse ATS handler."""
import logging

from playwright.sync_api import Page

from ..base_handler import BaseATSHandler, FormPage, PageResult

logger = logging.getLogger(__name__)


class GreenhouseHandler(BaseATSHandler):
    """Handler for Greenhouse ATS applications."""

    ATS_NAME = "greenhouse"

    APPLY_BUTTON_SELECTORS = [
        '#grnhse_app button:has-text("Apply")',
        'a:has-text("Apply for this job")',
        'button:has-text("Apply Now")',
    ]

    NEXT_BUTTON_SELECTORS = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Submit Application")',
        'button:has-text("Submit")',
    ]

    SUBMIT_BUTTON_SELECTORS = NEXT_BUTTON_SELECTORS

    FIELD_SELECTORS = {
        "first_name": [
            "#first_name",
            'input[name="first_name"]',
            'input[autocomplete="given-name"]',
        ],
        "last_name": [
            "#last_name",
            'input[name="last_name"]',
            'input[autocomplete="family-name"]',
        ],
        "email": [
            "#email",
            'input[name="email"]',
            'input[type="email"]',
        ],
        "phone": [
            "#phone",
            'input[name="phone"]',
            'input[type="tel"]',
        ],
        "resume": [
            'input[type="file"][name*="resume"]',
            "#resume_file",
            'input[data-field="resume"]',
        ],
        "cover_letter": [
            'input[type="file"][name*="cover"]',
            "#cover_letter_file",
        ],
        "linkedin": [
            'input[name*="linkedin"]',
            'input[placeholder*="LinkedIn"]',
        ],
        "website": [
            'input[name*="website"]',
            'input[name*="portfolio"]',
        ],
        "location": [
            'input[name*="location"]',
            "#location",
        ],
    }

    PAGE_INDICATORS = {
        FormPage.JOB_LISTING: [
            "#grnhse_app",
            ".job-post",
        ],
        FormPage.PERSONAL_INFO: [
            "#application_form",
            "form.application-form",
        ],
        FormPage.CONFIRMATION: [
            ".success-message",
            'text="Application submitted"',
            'text="Thank you for applying"',
        ],
    }

    def detect_page_type(self) -> FormPage:
        """Detect current Greenhouse page type."""
        for selector in self.PAGE_INDICATORS[FormPage.CONFIRMATION]:
            if self._is_visible(selector, timeout=500):
                return FormPage.CONFIRMATION

        for selector in self.PAGE_INDICATORS[FormPage.PERSONAL_INFO]:
            if self._is_visible(selector, timeout=500):
                return FormPage.PERSONAL_INFO

        return FormPage.JOB_LISTING

    def fill_current_page(self) -> PageResult:
        """Fill Greenhouse application form."""
        page_type = self.detect_page_type()

        if page_type == FormPage.CONFIRMATION:
            return PageResult(True, page_type, "Application submitted", False)

        if page_type == FormPage.JOB_LISTING:
            if self.click_apply():
                self._wait(1500)

        return self._fill_application_form()

    def _fill_application_form(self) -> PageResult:
        """Fill the main application form."""
        filled = self._fill_basic_fields()
        self._fill_optional_fields()
        self._upload_resume()
        self._handle_custom_questions()

        if self.click_submit():
            self._wait(3000)
            if self.detect_page_type() == FormPage.CONFIRMATION:
                return PageResult(
                    True, FormPage.PERSONAL_INFO, "Application submitted", False
                )
            return PageResult(
                True, FormPage.PERSONAL_INFO, f"Filled {filled} fields, submitted", True
            )

        return PageResult(False, FormPage.PERSONAL_INFO, "Could not submit", False)

    def _fill_basic_fields(self) -> int:
        """Fill basic required fields."""
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
        self._fill_field(
            self.FIELD_SELECTORS["website"], self._profile.get("portfolio_url", "")
        )
        self._fill_field(
            self.FIELD_SELECTORS["location"], self._profile.get("location", "")
        )

    def _upload_resume(self) -> None:
        """Upload resume if path provided."""
        if self._resume_path:
            self._upload_file(self.FIELD_SELECTORS["resume"], self._resume_path)
            self._wait(1500)

    def _handle_custom_questions(self) -> None:
        """Handle common Greenhouse custom questions."""
        self._answer_dropdowns()
        self._check_all_checkboxes()

    def _answer_dropdowns(self) -> None:
        """Answer common dropdown questions."""
        auth_selectors = [
            'select[name*="authorized"]',
            'select:has(option:has-text("authorized"))',
        ]
        self._select_option(auth_selectors, "Yes")

        sponsor_selectors = [
            'select[name*="sponsorship"]',
            'select:has(option:has-text("sponsorship"))',
        ]
        self._select_option(sponsor_selectors, "No")

        source_selectors = [
            'select[name*="source"]',
            'select[name*="hear"]',
        ]
        self._select_option(source_selectors, "Job Board")

    def _check_all_checkboxes(self) -> None:
        """Check all visible checkboxes."""
        try:
            checkboxes = self._page.locator('input[type="checkbox"]:visible')
            for i in range(checkboxes.count()):
                cb = checkboxes.nth(i)
                if not cb.is_checked():
                    cb.check()
        except Exception:
            pass
