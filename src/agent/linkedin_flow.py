"""LinkedIn Easy Apply flow handler."""
import logging
from typing import Optional

from ..browser.page import Page
from ..browser.tabs import TabManager
from ..extractor.dom_service import DomService
from .claude import ClaudeAgent
from ..executor.runner import ActionRunner
from .page_classifier import PageClassifier, PageType
from .models import JobSource, ApplicationStatus, ApplicationResult
from .form_processor import FormProcessor

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

    def apply(self, job_url: str) -> ApplicationResult:
        """
        Handle LinkedIn Easy Apply flow.

        Easy Apply opens a modal on the same page - no navigation required.
        LinkedIn uses SPA routing which can cause ERR_ABORTED on goto().
        """
        logger.info("Using LinkedIn Easy Apply flow")

        try:
            self._page.goto(job_url)
        except Exception as e:
            error_msg = str(e).lower()
            if "err_aborted" in error_msg or "aborted" in error_msg:
                logger.warning(f"Navigation aborted (LinkedIn SPA behavior): {e}")
                self._page.wait(2000)

                current_url = self._page.url.lower()
                if "linkedin.com/jobs" not in current_url:
                    logger.error(f"Navigation failed - not on LinkedIn jobs: {current_url}")
                    return ApplicationResult(
                        status=ApplicationStatus.ERROR,
                        message="Navigation to job page failed",
                        url=job_url
                    )
                logger.info(f"SPA navigation succeeded, now at: {self._page.url}")
            else:
                raise

        self._page.wait(2000)

        try:
            self._page.raw.wait_for_load_state("networkidle", timeout=5000)
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

        if not classifier.click_apply_button():
            return ApplicationResult(
                status=ApplicationStatus.NO_APPLY_BUTTON,
                message="Could not find Easy Apply button",
                url=job_url
            )

        self._page.wait(1500)

        if page_type == PageType.EXTERNAL_LINK:
            popup_url = self._tabs.get_captured_popup_url()
            if popup_url and popup_url != "about:blank":
                logger.info(f"External job: navigating to popup {popup_url}")
                self._page.goto(popup_url)
                self._page.wait(2000)
                self._tabs.close_extras(keep=1)

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
