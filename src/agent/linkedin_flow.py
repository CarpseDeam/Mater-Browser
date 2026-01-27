"""LinkedIn Easy Apply flow handler."""
import logging
from typing import Optional

from ..browser.page import Page
from ..browser.tabs import TabManager
from ..extractor.dom_service import DomService
from .claude import ClaudeAgent
from ..executor.runner import ActionRunner
from .page_classifier import PageClassifier, PageType
from .models import (
    JobSource,
    ApplicationStatus,
    ApplicationResult,
    MEDIUM_WAIT_MS,
    LONG_WAIT_MS,
    PAGE_LOAD_TIMEOUT_MS,
    MAX_POPUP_WAIT_ATTEMPTS,
)
from .form_processor import FormProcessor
from .answer_engine import AnswerEngine
from .linkedin_form_filler import LinkedInFormFiller

logger = logging.getLogger(__name__)


class LinkedInFlow:
    """Handles LinkedIn Easy Apply flow."""

    def __init__(
        self,
        page: Page,
        tabs: TabManager,
        claude: ClaudeAgent,
        profile: dict,
        resume_path: Optional[str],
        timeout_seconds: float,
        max_pages: int,
    ) -> None:
        self._page = page
        self._tabs = tabs
        self._claude = claude
        self._profile = profile
        self._resume_path = resume_path
        self._timeout_seconds = timeout_seconds
        self._max_pages = max_pages

    def _wait_for_external_popup(
        self, max_attempts: int = MAX_POPUP_WAIT_ATTEMPTS, delay_ms: int = MEDIUM_WAIT_MS
    ) -> Optional[str]:
        """Poll for captured popup URL with retries.

        Args:
            max_attempts: Maximum number of polling attempts.
            delay_ms: Delay between attempts in milliseconds.

        Returns:
            Captured popup URL or None if not found.
        """
        for attempt in range(max_attempts):
            url = self._tabs.get_captured_popup_url()
            if url and url != "about:blank":
                logger.info(f"Popup URL found on attempt {attempt + 1}: {url}")
                return url
            if attempt < max_attempts - 1:
                self._page.wait(delay_ms)
        logger.warning(f"No popup URL captured after {max_attempts} attempts")
        return None

    def apply(self, job_url: str) -> ApplicationResult:
        """
        Handle LinkedIn Easy Apply flow.

        Easy Apply opens a modal on the same page - no navigation required.
        LinkedIn uses SPA routing which can cause ERR_ABORTED on goto().
        """
        logger.info("Using LinkedIn Easy Apply flow")

        if not self._page.goto(job_url):
            return ApplicationResult(
                status=ApplicationStatus.ERROR,
                message="Navigation to job page failed",
                url=job_url,
            )

        self._page.wait(LONG_WAIT_MS)

        try:
            self._page.raw.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
        except Exception:
            pass

        classifier = PageClassifier(self._page.raw)
        page_type = classifier.classify()
        logger.info(f"Page classification: {page_type.value}")

        if page_type == PageType.PAYMENT_DANGER:
            logger.warning(f"PAYMENT PAGE DETECTED - aborting application: {self._page.url}")
            return ApplicationResult(
                status=ApplicationStatus.FAILED,
                message="Payment page detected - safety abort",
                url=job_url,
            )

        if page_type == PageType.ACCOUNT_CREATION:
            logger.warning(f"ACCOUNT CREATION PAGE DETECTED - aborting: {self._page.url}")
            return ApplicationResult(
                status=ApplicationStatus.FAILED,
                message="Account creation page detected - safety abort",
                url=job_url,
            )

        if page_type == PageType.LOGIN_REQUIRED:
            return ApplicationResult(
                status=ApplicationStatus.NEEDS_LOGIN,
                message="Login required for LINKEDIN - please authenticate in browser",
                url=job_url,
            )

        if page_type == PageType.ALREADY_APPLIED:
            return ApplicationResult(
                status=ApplicationStatus.FAILED,
                message="Already applied to this job",
                url=job_url,
            )

        if page_type == PageType.CLOSED:
            return ApplicationResult(
                status=ApplicationStatus.FAILED,
                message="Job is closed or no longer accepting applications",
                url=job_url,
            )

        if page_type == PageType.EXTERNAL_LINK:
            logger.info("External job detected - skipping (Easy Apply only)")
            return ApplicationResult(
                status=ApplicationStatus.SKIPPED,
                message="External application - Easy Apply only",
                url=job_url,
            )

        if not classifier.click_apply_button():
            return ApplicationResult(
                status=ApplicationStatus.NO_APPLY_BUTTON,
                message="Could not find Easy Apply button",
                url=job_url,
            )

        self._page.wait(MEDIUM_WAIT_MS)

        if page_type == PageType.EASY_APPLY:
            return self._process_easy_apply(job_url)

        return self._process_with_claude_fallback(job_url)

    def _process_easy_apply(self, job_url: str) -> ApplicationResult:
        """Process LinkedIn Easy Apply using deterministic form filler."""
        logger.info("Using deterministic form filler for Easy Apply")

        answer_engine = AnswerEngine()
        filler = LinkedInFormFiller(self._page.raw, answer_engine)

        for page_num in range(self._max_pages):
            self._page.wait(1000)

            if filler.is_confirmation_page():
                filler.close_modal()
                return ApplicationResult(
                    status=ApplicationStatus.SUCCESS,
                    message="Application submitted",
                    pages_processed=page_num + 1,
                    url=job_url,
                )

            success, unknown = filler.fill_current_modal()

            if unknown:
                logger.warning(f"Skipping job - unknown questions: {unknown[:3]}")
                filler.close_modal()
                return ApplicationResult(
                    status=ApplicationStatus.FAILED,
                    message=f"Unknown questions: {', '.join(unknown[:3])}",
                    pages_processed=page_num + 1,
                    url=job_url,
                )

            if not filler.click_next():
                logger.warning("Could not find next button")
                break

            self._page.wait(1000)

        return ApplicationResult(
            status=ApplicationStatus.FAILED,
            message="Max pages reached or stuck",
            pages_processed=self._max_pages,
            url=job_url,
        )

    def _process_with_claude_fallback(self, job_url: str) -> ApplicationResult:
        """Fallback to Claude-based processing for external/unknown pages."""
        dom_service = DomService(self._page)
        runner = ActionRunner(self._page, dom_service)

        processor = FormProcessor(
            page=self._page,
            dom_service=dom_service,
            claude=self._claude,
            runner=runner,
            tabs=self._tabs,
            profile=self._profile,
            resume_path=self._resume_path,
            timeout_seconds=self._timeout_seconds,
            max_pages=self._max_pages,
        )

        return processor.process(job_url, source=JobSource.LINKEDIN)
