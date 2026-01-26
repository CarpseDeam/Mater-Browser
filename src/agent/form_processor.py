"""Form processing logic for multi-page application flows."""
import logging
import re
import time
from typing import Optional

from ..browser.page import Page
from ..browser.tabs import TabManager
from ..extractor.dom_service import DomService
from .claude import ClaudeAgent
from ..executor.runner import ActionRunner
from .page_classifier import PageClassifier
from .loop_detector import LoopDetector, MAX_SAME_STATE_COUNT
from .models import (
    JobSource, ApplicationStatus, ApplicationResult,
    ACCOUNT_CREATION_URL_PATTERNS, ACCOUNT_CREATION_CONTENT,
)
from .indeed_helpers import IndeedHelpers

logger = logging.getLogger(__name__)

COMPLETION_PHRASES: list[str] = [
    "thank you for applying", "application submitted", "application received",
    "we have received your application", "your application has been submitted",
    "your application was sent", "application was sent",
]
NEGATIVE_URL_SIGNALS: list[str] = [
    "/job/", "/jobs/", "/careers/", "/viewjob", "/job-detail", "/apply", "linkedin.com/jobs/view"
]
POSITIVE_URL_SIGNALS: list[str] = ["success", "submitted", "confirmed", "thank", "complete", "post-apply", "postApplyJobId", "confirmation"]


class FormProcessor:
    """Processes multi-page application forms."""

    def __init__(
        self, page: Page, dom_service: DomService, claude: ClaudeAgent,
        runner: ActionRunner, tabs: TabManager, profile: dict,
        resume_path: Optional[str], timeout_seconds: float, max_pages: int,
    ) -> None:
        self._page = page
        self._dom_service = dom_service
        self._claude = claude
        self._runner = runner
        self._tabs = tabs
        self._profile = profile
        self._resume_path = resume_path
        self._timeout_seconds = timeout_seconds
        self._max_pages = max_pages
        self._loop_detector = LoopDetector()
        self._indeed_helpers = IndeedHelpers(page)

    def process(self, job_url: str, source: Optional[JobSource] = None) -> ApplicationResult:
        """Process multi-page application form."""
        pages_processed = 0
        stuck_count = 0
        last_url = ""
        start_time = time.time()

        while pages_processed < self._max_pages:
            elapsed = time.time() - start_time
            if elapsed > self._timeout_seconds:
                logger.warning(f"Application timed out after {elapsed:.1f}s")
                return ApplicationResult(ApplicationStatus.STUCK, f"Timed out after {elapsed:.1f}s", pages_processed, job_url)
            pages_processed += 1

            if source == JobSource.INDEED and self._indeed_helpers.dismiss_modal():
                pages_processed -= 1
                continue

            current_url = self._page.url

            if PageClassifier(self._page.raw)._is_payment_page():
                logger.warning(f"PAYMENT PAGE DETECTED - aborting: {current_url}")
                return ApplicationResult(ApplicationStatus.FAILED, "Payment page detected - safety abort", pages_processed, job_url)

            try:
                page_text = self._page.raw.content()[:5000]
            except Exception:
                page_text = ""

            if self._is_account_creation_page(current_url, page_text):
                logger.warning(f"ACCOUNT CREATION PAGE DETECTED - aborting: {current_url}")
                return ApplicationResult(ApplicationStatus.FAILED, "Requires account creation", pages_processed, job_url)

            logger.info(f"=== Page {pages_processed} === URL: {current_url}")

            if self._is_complete(pages_processed):
                return ApplicationResult(ApplicationStatus.SUCCESS, "Application submitted successfully", pages_processed, job_url)

            if self._indeed_helpers.handle_resume_card():
                self._page.wait(1500)
                if self._is_complete(pages_processed):
                    return ApplicationResult(ApplicationStatus.SUCCESS, "Application submitted successfully", pages_processed, job_url)
                continue

            dom_state = self._dom_service.extract()
            logger.info(f"Found {dom_state.elementCount} elements")

            self._loop_detector.record_state(current_url, dom_state.elementCount)
            if self._loop_detector.is_looping():
                logger.warning(f"LOOP DETECTED - same state {MAX_SAME_STATE_COUNT} times")
                return ApplicationResult(ApplicationStatus.FAILED, "Stuck in form loop", pages_processed, job_url)

            if dom_state.elementCount == 0:
                stuck_count += 1
                if stuck_count >= 3:
                    return ApplicationResult(ApplicationStatus.STUCK, "No interactive elements found", pages_processed, job_url)
                self._page.wait(2000)
                continue

            plan = self._claude.analyze_form(dom_state, self._profile, self._dom_service)
            if not plan:
                stuck_count += 1
                if stuck_count >= 3:
                    return ApplicationResult(ApplicationStatus.STUCK, "Failed to analyze form", pages_processed, job_url)
                continue

            self._indeed_helpers.try_resume_upload(dom_state, self._resume_path, self._dom_service)
            logger.info(f"Executing plan: {plan.reasoning}")
            success = self._runner.execute(plan)

            if source == JobSource.INDEED:
                self._indeed_helpers.dismiss_modal()
            if not success:
                logger.warning("Plan execution had errors")

            self._page.wait(1500)
            self._handle_new_tab()

            new_url = self._page.url
            if new_url == last_url == current_url:
                if not self._click_next_button():
                    stuck_count += 1
                    if stuck_count >= 3:
                        return ApplicationResult(ApplicationStatus.STUCK, "Could not advance to next page", pages_processed, job_url)
            else:
                stuck_count = 0
            last_url = current_url

        return ApplicationResult(ApplicationStatus.MAX_PAGES_REACHED, f"Reached max pages ({self._max_pages})", pages_processed, job_url)

    def _is_account_creation_page(self, url: str, page_text: str) -> bool:
        url_lower = url.lower()
        if any(p in url_lower for p in ACCOUNT_CREATION_URL_PATTERNS):
            return True
        text_lower = page_text.lower()
        return sum(1 for phrase in ACCOUNT_CREATION_CONTENT if phrase in text_lower) >= 2

    def _handle_new_tab(self) -> None:
        popup_url = self._tabs.get_captured_popup_url()
        if popup_url and popup_url != "about:blank":
            logger.info(f"Popup captured, navigating to: {popup_url}")
            try:
                self._page.goto(popup_url)
            except Exception as e:
                if "err_aborted" not in str(e).lower() and "aborted" not in str(e).lower():
                    raise
                self._page.wait(2000)
            self._dom_service = DomService(self._page)
            self._runner = ActionRunner(self._page, self._dom_service)
            self._page.wait(2000)
            self._tabs.close_extras(keep=1)

    def _click_next_button(self) -> bool:
        page = self._page.raw
        next_locator = (
            page.get_by_role("button", name=re.compile(r"next|continue|submit|review", re.IGNORECASE))
            .or_(page.get_by_role("link", name=re.compile(r"next|continue", re.IGNORECASE)))
            .or_(page.locator('[type="submit"]'))
            .or_(page.locator('[aria-label*="Next" i], [aria-label*="Continue" i], [aria-label*="Submit" i]'))
            .or_(page.locator('[data-testid*="next" i], [data-testid*="submit" i]'))
        )
        try:
            first_match = next_locator.first
            if first_match.is_visible(timeout=3000):
                first_match.click()
                self._page.wait(1500)
                logger.info("Clicked Next button successfully")
                return True
        except Exception as e:
            logger.debug(f"Next button locator failed: {e}")
        return False

    def _is_complete(self, pages_processed: int = 0) -> bool:
        if pages_processed < 2:
            return False
        page = self._page.raw
        current_url = self._page.url.lower()

        if any(sig in current_url for sig in NEGATIVE_URL_SIGNALS):
            if not any(pos in current_url for pos in POSITIVE_URL_SIGNALS):
                return False

        completion_locator = (
            page.get_by_text(re.compile(r"application submitted|thank you for applying|successfully submitted|application received|application was sent", re.IGNORECASE))
            .or_(page.locator('[data-test="application-complete"], [data-testid*="success" i], [data-testid*="complete" i]'))
            .or_(page.locator('.application-complete, #application-success, [class*="success"][class*="message" i]'))
        )
        try:
            if completion_locator.first.is_visible(timeout=1000):
                logger.info("Completion indicator found")
                return True
        except Exception:
            pass

        try:
            content = page.content().lower()
            if any(phrase in content for phrase in COMPLETION_PHRASES):
                logger.info("Completion detected via page content")
                return True
        except Exception:
            pass
        return False
