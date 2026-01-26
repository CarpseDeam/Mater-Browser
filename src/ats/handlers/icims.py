"""iCIMS ATS handler."""
import logging

from ..base_handler import BaseATSHandler, FormPage, PageResult

logger = logging.getLogger(__name__)


class ICIMSHandler(BaseATSHandler):
    """Handler for iCIMS ATS applications."""

    ATS_NAME = "icims"

    APPLY_BUTTON_SELECTORS = [
        "#link-apply",
        'a:has-text("Apply")',
        'button:has-text("Apply")',
        ".iCIMS_ApplyButton",
    ]

    NEXT_BUTTON_SELECTORS = [
        "#next",
        'button:has-text("Next")',
        'button:has-text("Continue")',
        'input[type="submit"][value*="Next"]',
    ]

    SUBMIT_BUTTON_SELECTORS = [
        "#submit",
        'button:has-text("Submit")',
        'input[type="submit"][value*="Submit"]',
    ]

    FIELD_SELECTORS = {
        "first_name": [
            "#Contact_Information_firstname",
            'input[name*="firstname" i]',
        ],
        "last_name": [
            "#Contact_Information_lastname",
            'input[name*="lastname" i]',
        ],
        "email": [
            "#Contact_Information_email",
            'input[name*="email" i]',
            'input[type="email"]',
        ],
        "phone": [
            "#Contact_Information_phone",
            'input[name*="phone" i]',
            'input[type="tel"]',
        ],
        "city": [
            "#Contact_Information_city",
            'input[name*="city" i]',
        ],
        "resume": [
            'input[type="file"]',
            "#resumeUpload",
        ],
    }

    PAGE_INDICATORS = {
        FormPage.LOGIN: [
            'input[type="password"]',
            'text="Sign In"',
            "#login",
        ],
        FormPage.PERSONAL_INFO: [
            "#Contact_Information_email",
            'text="Contact Information"',
        ],
        FormPage.QUESTIONS: [
            'text="Position Specific Questions"',
            '[id*="Position_Specific"]',
        ],
        FormPage.REVIEW: [
            'text="Review"',
            'text="Summary"',
        ],
        FormPage.CONFIRMATION: [
            'text="Thank you"',
            'text="successfully"',
            'text="Application Submitted"',
        ],
    }

    def detect_page_type(self) -> FormPage:
        """Detect current iCIMS page type."""
        url = self._page.url.lower()

        if "/login" in url:
            return FormPage.LOGIN

        for page_type, selectors in self.PAGE_INDICATORS.items():
            for selector in selectors:
                if self._is_visible(selector, timeout=500):
                    logger.info(f"iCIMS page type: {page_type.value}")
                    return page_type
        return FormPage.UNKNOWN

    def fill_current_page(self) -> PageResult:
        """Fill current iCIMS page."""
        page_type = self.detect_page_type()

        handlers = {
            FormPage.LOGIN: lambda: PageResult(
                False, page_type, "Login required - cannot proceed", False
            ),
            FormPage.PERSONAL_INFO: self._handle_personal_info,
            FormPage.QUESTIONS: self._handle_questions,
            FormPage.REVIEW: self._handle_review,
            FormPage.CONFIRMATION: lambda: PageResult(
                True, page_type, "Application submitted", False
            ),
        }

        handler = handlers.get(page_type, self._handle_unknown)
        return handler()

    def _handle_personal_info(self) -> PageResult:
        """Fill personal info page."""
        filled = self._fill_basic_fields()
        self._upload_resume()

        if self.click_next():
            return PageResult(
                True, FormPage.PERSONAL_INFO, f"Filled {filled} fields", True
            )
        return PageResult(False, FormPage.PERSONAL_INFO, "Could not advance", False)

    def _fill_basic_fields(self) -> int:
        """Fill basic contact fields."""
        filled = 0
        fields = [
            ("first_name", "first_name"),
            ("last_name", "last_name"),
            ("email", "email"),
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

    def _handle_questions(self) -> PageResult:
        """Handle screening questions."""
        self._answer_work_auth_questions()
        self._check_all_consent_boxes()

        if self.click_next():
            return PageResult(True, FormPage.QUESTIONS, "Answered questions", True)
        return PageResult(False, FormPage.QUESTIONS, "Could not advance", False)

    def _handle_review(self) -> PageResult:
        """Submit application."""
        self._check_all_consent_boxes()

        if self.click_submit():
            self._wait(3000)
            return PageResult(True, FormPage.REVIEW, "Submitted", False)
        return PageResult(False, FormPage.REVIEW, "Could not submit", False)

    def _handle_unknown(self) -> PageResult:
        """Try to advance unknown page."""
        if self.click_next():
            return PageResult(True, FormPage.UNKNOWN, "Advanced", True)
        if self.click_submit():
            return PageResult(True, FormPage.UNKNOWN, "Submitted", False)
        return PageResult(False, FormPage.UNKNOWN, "Stuck", False)

    def _answer_work_auth_questions(self) -> None:
        """Answer common work authorization questions."""
        work_auth = self._profile.get("extra", {}).get("work_authorization", True)

        if work_auth:
            try:
                yes_buttons = self._page.locator('label:has-text("Yes")').all()
                for btn in yes_buttons[:2]:
                    btn.click()
            except Exception:
                pass

    def _check_all_consent_boxes(self) -> None:
        """Check all consent/agreement checkboxes."""
        try:
            checkboxes = self._page.locator('input[type="checkbox"]:visible').all()
            for cb in checkboxes:
                if not cb.is_checked():
                    cb.check()
        except Exception:
            pass
