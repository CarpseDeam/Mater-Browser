"""ATS detection from URL patterns and page signatures."""
import logging
import re
from enum import Enum
from typing import Optional

from playwright.sync_api import Page

logger = logging.getLogger(__name__)


class ATSType(Enum):
    """Known ATS systems."""
    WORKDAY = "workday"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ICIMS = "icims"
    PHENOM = "phenom"
    SMARTRECRUITERS = "smartrecruiters"
    TALEO = "taleo"
    INDEED_EASY = "indeed_easy"
    LINKEDIN_EASY = "linkedin_easy"
    UNKNOWN = "unknown"


ATS_URL_PATTERNS: dict[ATSType, list[str]] = {
    ATSType.WORKDAY: [
        r"myworkdayjobs\.com",
        r"wd\d+\.myworkday\.com",
        r"workday\.com/.*recruit",
    ],
    ATSType.GREENHOUSE: [
        r"boards\.greenhouse\.io",
        r"job-boards\.greenhouse\.io",
        r"greenhouse\.io/.*jobs",
    ],
    ATSType.LEVER: [
        r"jobs\.lever\.co",
        r"lever\.co/.*apply",
    ],
    ATSType.ICIMS: [
        r"careers-.*\.icims\.com",
        r"\.icims\.com/jobs",
    ],
    ATSType.PHENOM: [
        r"phenom\.com",
        r"/us/en/job/",
        r"/careers-home/jobs/",
    ],
    ATSType.SMARTRECRUITERS: [
        r"jobs\.smartrecruiters\.com",
        r"smartrecruiters\.com/.*jobs",
    ],
    ATSType.TALEO: [
        r"taleo\.net",
        r"\.taleo\.net/careersection",
    ],
    ATSType.INDEED_EASY: [
        r"smartapply\.indeed\.com",
        r"indeed\.com/applystart",
    ],
    ATSType.LINKEDIN_EASY: [
        r"linkedin\.com/jobs/view/.*/apply",
    ],
}

ATS_PAGE_SIGNATURES: dict[ATSType, list[str]] = {
    ATSType.WORKDAY: [
        '[data-automation-id="workday"]',
        '[class*="workday"]',
        'form[data-automation-id]',
    ],
    ATSType.GREENHOUSE: [
        '#grnhse_app',
        '[class*="greenhouse"]',
        'form#application_form',
    ],
    ATSType.LEVER: [
        '[class*="lever"]',
        'form.application-form',
        '[data-qa="application-form"]',
    ],
    ATSType.ICIMS: [
        '[class*="icims"]',
        '#iCIMS_Content',
        'form.iCIMS_Form',
    ],
    ATSType.PHENOM: [
        '[class*="phenom"]',
        '[data-ph-at-id]',
        '.ph-form-container',
    ],
}


class ATSDetector:
    """Detects ATS system from URL and page content."""

    def __init__(self, page: Page) -> None:
        self._page = page

    def detect(self) -> ATSType:
        """Detect ATS type from current page."""
        url = self._page.url.lower()

        ats_type = self._detect_from_url(url)
        if ats_type != ATSType.UNKNOWN:
            return ats_type

        return self._detect_from_signatures()

    def _detect_from_url(self, url: str) -> ATSType:
        """Detect ATS from URL patterns."""
        for ats_type, patterns in ATS_URL_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    logger.info(f"ATS detected via URL: {ats_type.value}")
                    return ats_type
        return ATSType.UNKNOWN

    def _detect_from_signatures(self) -> ATSType:
        """Detect ATS from page DOM signatures."""
        for ats_type, selectors in ATS_PAGE_SIGNATURES.items():
            for selector in selectors:
                try:
                    if self._page.locator(selector).count() > 0:
                        logger.info(f"ATS detected via signature: {ats_type.value}")
                        return ats_type
                except Exception:
                    continue

        logger.info("ATS type: unknown")
        return ATSType.UNKNOWN
