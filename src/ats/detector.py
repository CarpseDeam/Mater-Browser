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
    INDEED = "indeed"
    LINKEDIN = "linkedin"
    UNKNOWN = "unknown"


# URL patterns for each ATS - order matters, more specific first
ATS_URL_PATTERNS: dict[ATSType, list[str]] = {
    ATSType.WORKDAY: [
        r"myworkdayjobs\.com",
        r"workday\.com/.*jobs",
        r"wd\d+\.myworkdayjobs",
    ],
    ATSType.GREENHOUSE: [
        r"boards\.greenhouse\.io",
        r"greenhouse\.io/.*jobs",
        r"/gh_jid=",
    ],
    ATSType.LEVER: [
        r"jobs\.lever\.co",
        r"lever\.co/.*apply",
    ],
    ATSType.ICIMS: [
        r"icims\.com",
        r"careers-.*\.icims\.com",
        r"\.icims\.com/jobs",
    ],
    ATSType.PHENOM: [
        r"phenom\.com",
        r"/us/en/job/",
        r"/us/en/apply",
    ],
    ATSType.SMARTRECRUITERS: [
        r"jobs\.smartrecruiters\.com",
        r"smartrecruiters\.com/.*jobs",
    ],
    ATSType.TALEO: [
        r"taleo\.net",
        r"\.taleo\.net/careersection",
        r"oracle.*taleo",
    ],
    ATSType.INDEED: [
        r"smartapply\.indeed\.com",
        r"indeed\.com/applystart",
        r"indeedapply",
    ],
    ATSType.LINKEDIN: [
        r"linkedin\.com/jobs",
    ],
}

# Page signatures - CSS selectors that indicate specific ATS
ATS_PAGE_SIGNATURES: dict[ATSType, list[str]] = {
    ATSType.WORKDAY: [
        "[data-automation-id='workday']",
        "[data-automation-id='jobPostingPage']",
        ".WD-",
        "[class*='workday']",
    ],
    ATSType.GREENHOUSE: [
        "#greenhouse-app",
        "[data-greenhouse]",
        ".greenhouse-application",
        "#application_form",
    ],
    ATSType.LEVER: [
        ".lever-application",
        "[data-lever]",
        ".lever-job-posting",
    ],
    ATSType.ICIMS: [
        "[class*='icims']",
        "#icims_content",
        ".iCIMS_",
    ],
    ATSType.PHENOM: [
        "[data-ph-id]",
        ".ph-",
        "[class*='phenom']",
    ],
    ATSType.SMARTRECRUITERS: [
        "[class*='smartrecruiters']",
        ".sr-",
        "[data-sr]",
    ],
    ATSType.TALEO: [
        "[class*='taleo']",
        ".taleo-",
        "#taleo",
    ],
    ATSType.INDEED: [
        "[data-testid='indeedApply']",
        ".indeed-apply",
        "[class*='ia-']",
    ],
}


class ATSDetector:
    """Detects ATS type from URL and page content."""

    def __init__(self, page: Page) -> None:
        self._page = page

    def detect(self) -> ATSType:
        """Detect ATS type. Checks URL first, then page signatures."""
        url_match = self._detect_from_url()
        if url_match != ATSType.UNKNOWN:
            logger.info(f"ATS detected from URL: {url_match.value}")
            return url_match

        sig_match = self._detect_from_signatures()
        if sig_match != ATSType.UNKNOWN:
            logger.info(f"ATS detected from page signature: {sig_match.value}")
            return sig_match

        logger.warning("Could not detect ATS type")
        return ATSType.UNKNOWN

    def _detect_from_url(self) -> ATSType:
        """Match URL against known ATS patterns."""
        url = self._page.url.lower()
        for ats_type, patterns in ATS_URL_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return ats_type
        return ATSType.UNKNOWN

    def _detect_from_signatures(self) -> ATSType:
        """Check page for ATS-specific elements."""
        for ats_type, selectors in ATS_PAGE_SIGNATURES.items():
            for selector in selectors:
                try:
                    if self._page.locator(selector).count() > 0:
                        return ats_type
                except Exception:
                    continue
        return ATSType.UNKNOWN
