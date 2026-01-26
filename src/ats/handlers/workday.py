"""Workday ATS handler."""
import logging
from typing import Optional

from playwright.sync_api import Page

from ..base_handler import BaseATSHandler, FormPage, PageResult

logger = logging.getLogger(__name__)


class WorkdayHandler(BaseATSHandler):
    """Handler for Workday ATS applications."""

    ATS_NAME = "workday"

    APPLY_BUTTON_SELECTORS = [
        '[data-automation-id="jobPostingApplyButton"]',
        'button[data-automation-id="applyButton"]',
        'a[data-automation-id="applyButton"]',
        'button:has-text("Apply")',
    ]

    NEXT_BUTTON_SELECTORS = [
        '[data-automation-id="bottom-navigation-next-button"]',
        '[data-automation-id="nextButton"]',
        'button:has-text("Next")',
        'button:has-text("Continue")',
    ]

    SUBMIT_BUTTON_SELECTORS = [
        '[data-automation-id="bottom-navigation-submit-button"]',
        '[data-automation-id="submitButton"]',
        'button:has-text("Submit")',
    ]

    FIELD_SELECTORS = {
        "first_name": [
            '[data-automation-id="legalNameSection_firstName"]',
            'input[data-automation-id="firstName"]',
        ],
        "last_name": [
            '[data-automation-id="legalNameSection_lastName"]',
            'input[data-automation-id="lastName"]',
        ],
        "email": [
            '[data-automation-id="email"]',
            'input[data-automation-id="emailAddress"]',
        ],
        "phone": [
            '[data-automation-id="phone-number"]',
            'input[data-automation-id="phoneNumber"]',
        ],
        "address": [
            '[data-automation-id="addressSection_addressLine1"]',
        ],
        "city": [
            '[data-automation-id="addressSection_city"]',
        ],
        "state": [
            '[data-automation-id="addressSection_countryRegion"]',
        ],
        "postal_code": [
            '[data-automation-id="addressSection_postalCode"]',
        ],
        "country": [
            '[data-automation-id="addressSection_country"]',
        ],
        "resume": [
            'input[data-automation-id="file-upload-input-ref"]',
            '[data-automation-id="resumeUpload"] input[type="file"]',
        ],
        "linkedin": [
            '[data-automation-id="linkedInUrl"]',
            'input[placeholder*="linkedin"]',
        ],
    }

    PAGE_INDICATORS = {
        FormPage.JOB_LISTING: [
            '[data-automation-id="jobPostingHeader"]',
            '[data-automation-id="jobPostingApplyButton"]',
        ],
        FormPage.PERSONAL_INFO: [
            '[data-automation-id="legalNameSection"]',
            '[data-automation-id="contactInformationSection"]',
        ],
        FormPage.EXPERIENCE: [
            '[data-automation-id="workExperienceSection"]',
            '[data-automation-id="Add Work Experience"]',
        ],
        FormPage.EDUCATION: [
            '[data-automation-id="educationSection"]',
            '[data-automation-id="Add Education"]',
        ],
        FormPage.DOCUMENTS: [
            '[data-automation-id="resumeSection"]',
            '[data-automation-id="file-upload"]',
        ],
        FormPage.REVIEW: [
            '[data-automation-id="reviewSection"]',
            'text="Review your application"',
        ],
        FormPage.CONFIRMATION: [
            '[data-automation-id="applicationSuccessMessage"]',
            'text="Application submitted"',
            'text="Thank you"',
        ],
    }

    def detect_page_type(self) -> FormPage:
        """Detect current Workday page type."""
        for page_type, selectors in self.PAGE_INDICATORS.items():
            for selector in selectors:
                if self._is_visible(selector, timeout=500):
                    logger.info(f"Workday page type: {page_type.value}")
                    return page_type
        return FormPage.UNKNOWN

    def fill_current_page(self) -> PageResult:
        """Fill all fields on the current Workday page."""
        page_type = self.detect_page_type()

        handlers = {
            FormPage.JOB_LISTING: self._handle_job_listing,
            FormPage.PERSONAL_INFO: self._handle_personal_info,
            FormPage.EXPERIENCE: self._handle_experience,
            FormPage.DOCUMENTS: self._handle_documents,
            FormPage.REVIEW: self._handle_review,
            FormPage.CONFIRMATION: lambda: PageResult(
                True, FormPage.CONFIRMATION, "Application submitted", False
            ),
        }

        handler = handlers.get(page_type, self._handle_unknown)
        return handler()

    def _handle_job_listing(self) -> PageResult:
        """Click Apply on job listing page."""
        if self.click_apply():
            self._wait(2000)
            return PageResult(True, FormPage.JOB_LISTING, "Clicked Apply", True)
        return PageResult(
            False, FormPage.JOB_LISTING, "Could not find Apply button", False
        )

    def _handle_personal_info(self) -> PageResult:
        """Fill personal information fields."""
        filled = self._fill_basic_info()
        filled += self._fill_location_info()
        self._fill_field(
            self.FIELD_SELECTORS["linkedin"], self._profile.get("linkedin_url", "")
        )

        if self.click_next():
            return PageResult(
                True, FormPage.PERSONAL_INFO, f"Filled {filled} fields", True
            )
        return PageResult(False, FormPage.PERSONAL_INFO, "Could not click Next", False)

    def _fill_basic_info(self) -> int:
        """Fill basic contact info fields."""
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

    def _fill_location_info(self) -> int:
        """Fill location fields from profile."""
        filled = 0
        location = self._profile.get("location", "")
        if not location:
            return filled

        parts = location.split(",")
        if len(parts) >= 1:
            if self._fill_field(self.FIELD_SELECTORS["city"], parts[0].strip()):
                filled += 1
        if len(parts) >= 2:
            if self._fill_field(self.FIELD_SELECTORS["state"], parts[1].strip()):
                filled += 1
        return filled

    def _handle_experience(self) -> PageResult:
        """Handle work experience page."""
        if self.click_next():
            return PageResult(
                True, FormPage.EXPERIENCE, "Skipped experience (resume uploaded)", True
            )
        return PageResult(False, FormPage.EXPERIENCE, "Could not advance", False)

    def _handle_documents(self) -> PageResult:
        """Upload resume."""
        if self._resume_path:
            self._upload_file(self.FIELD_SELECTORS["resume"], self._resume_path)
            self._wait(2000)

        if self.click_next():
            return PageResult(True, FormPage.DOCUMENTS, "Resume uploaded", True)
        return PageResult(False, FormPage.DOCUMENTS, "Could not advance", False)

    def _handle_review(self) -> PageResult:
        """Submit the application."""
        self._check_checkbox(['input[type="checkbox"]'])

        if self.click_submit():
            self._wait(3000)
            return PageResult(True, FormPage.REVIEW, "Application submitted", False)
        return PageResult(False, FormPage.REVIEW, "Could not submit", False)

    def _handle_unknown(self) -> PageResult:
        """Handle unknown page type."""
        if self.click_next():
            return PageResult(True, FormPage.UNKNOWN, "Advanced to next page", True)
        if self.click_submit():
            return PageResult(True, FormPage.UNKNOWN, "Submitted application", False)
        return PageResult(
            False, FormPage.UNKNOWN, "Could not determine page type", False
        )
