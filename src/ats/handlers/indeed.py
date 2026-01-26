"""Indeed Easy Apply handler."""
import logging
from typing import Optional

from playwright.sync_api import Page

from ..base_handler import BaseATSHandler, HandlerResult, PageState
from ..field_mapper import FieldMapper

logger = logging.getLogger(__name__)


class IndeedHandler(BaseATSHandler):
    """Handler for Indeed Easy Apply."""

    ATS_NAME = "indeed"

    APPLY_BUTTON_SELECTORS = [
        "[data-testid='indeedApply-button']",
        "button:has-text('Apply now')",
        "#indeedApplyButton",
        ".indeed-apply-button",
    ]

    NEXT_BUTTON_SELECTORS = [
        "[data-testid='ia-continueButton']",
        "button:has-text('Continue')",
        "button:has-text('Next')",
        "[data-tn-element='continueButton']",
    ]

    SUBMIT_BUTTON_SELECTORS = [
        "[data-testid='ia-submit-button']",
        "button:has-text('Submit')",
        "button:has-text('Submit your application')",
    ]

    def __init__(
        self, page: Page, profile: dict, resume_path: Optional[str] = None
    ) -> None:
        super().__init__(page, profile, resume_path)
        self._mapper = FieldMapper(profile)

    def detect_page_state(self) -> PageState:
        """Detect current Indeed page state."""
        url = self._page.url.lower()

        if self._is_confirmation_page(url):
            return PageState.CONFIRMATION

        if self._is_login_page(url):
            return PageState.LOGIN_REQUIRED

        if self._is_form_page(url):
            return PageState.FORM

        if self._is_job_listing_page(url):
            return PageState.JOB_LISTING

        return PageState.UNKNOWN

    def _is_confirmation_page(self, url: str) -> bool:
        """Check if current page is confirmation."""
        if "/post-apply" in url or "postApplyJobId" in url:
            return True
        if self._has_element("[data-testid='ia-success']"):
            return True
        if self._has_element(":has-text('Application submitted')"):
            return True
        return False

    def _is_login_page(self, url: str) -> bool:
        """Check if login is required."""
        if "/account/login" in url:
            return True
        return self._has_element("#loginForm")

    def _is_form_page(self, url: str) -> bool:
        """Check if current page is a form."""
        if "smartapply.indeed.com" in url:
            return True
        if "/review-module" in url or "/resume" in url:
            return True
        return False

    def _is_job_listing_page(self, url: str) -> bool:
        """Check if current page is job listing."""
        return "indeed.com/viewjob" in url

    def fill_current_page(self) -> HandlerResult:
        """Fill current Indeed page."""
        filled_count = 0
        url = self._page.url.lower()

        if "/resume" in url or self._has_element("[data-testid*='resume']"):
            if self._select_indeed_resume():
                return HandlerResult(
                    True, "Selected resume", PageState.FORM
                )

        filled_count += self._fill_contact_fields()
        self._handle_indeed_questions()
        self._handle_checkboxes()

        logger.info(f"{self.ATS_NAME}: Filled {filled_count} fields")
        return HandlerResult(
            True, f"Filled {filled_count} fields", PageState.FORM
        )

    def _fill_contact_fields(self) -> int:
        """Fill contact information fields."""
        filled = 0
        if self._fill_field("#firstName", self._profile.get("first_name", "")):
            filled += 1
        if self._fill_field("#lastName", self._profile.get("last_name", "")):
            filled += 1
        if self._fill_field("#email", self._profile.get("email", "")):
            filled += 1
        if self._fill_field("#phone", self._profile.get("phone", "")):
            filled += 1
        return filled

    def _select_indeed_resume(self) -> bool:
        """Select Indeed Resume card."""
        resume_selectors = [
            "[data-testid*='structured-resume'][data-testid*='card']",
            "[data-testid*='resume-selection']",
            "div:has-text('Indeed Resume')",
        ]
        for sel in resume_selectors:
            try:
                loc = self._page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    loc.click()
                    logger.info(f"{self.ATS_NAME}: Selected resume")
                    return True
            except Exception:
                continue
        return False

    def _handle_indeed_questions(self) -> None:
        """Handle common Indeed questions."""
        try:
            auth_yes = self._page.locator(
                "input[type='radio'][value='Yes']"
            ).first
            if auth_yes.is_visible(timeout=500):
                auth_yes.click()
        except Exception:
            pass

        try:
            no_radio = self._page.locator("label:has-text('No')").first
            if no_radio.is_visible(timeout=500):
                no_radio.click()
        except Exception:
            pass

    def _handle_checkboxes(self) -> None:
        """Check agreement boxes."""
        self._click_checkbox("[data-testid='agree-checkbox']")
        self._click_checkbox("input[type='checkbox'][required]")

    def advance_page(self) -> HandlerResult:
        """Click continue/submit button."""
        return self._click_next_button()
