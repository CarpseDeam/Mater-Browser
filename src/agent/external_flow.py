"""External job board apply flow handler (Indeed, Dice, direct sites)."""
import logging
import time
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
    LOGIN_URL_PATTERNS,
    EXTERNAL_REDIRECT_TIMEOUT_MS,
)
from .form_processor import FormProcessor

logger = logging.getLogger(__name__)


class ExternalFlow:
    """Handles external job board apply flow (Indeed, Dice, direct sites)."""

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

    def apply(self, job_url: str, source: JobSource) -> ApplicationResult:
        """
        Handle external job board apply flow.

        External applies redirect to an ATS (Greenhouse, Lever, Workday).
        We must wait for the redirect BEFORE extracting DOM.
        """
        logger.info(f"Using external apply flow for {source.value}")

        try:
            self._page.goto(job_url)
        except Exception as e:
            error_msg = str(e).lower()
            if "err_aborted" in error_msg or "aborted" in error_msg:
                logger.warning(f"Navigation aborted: {e}")
                self._page.wait(2000)
                if not self._page.url or self._page.url == "about:blank":
                    return ApplicationResult(
                        status=ApplicationStatus.ERROR,
                        message="Navigation failed completely",
                        url=job_url
                    )
                logger.info(f"Navigation recovered, now at: {self._page.url}")
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
                message=f"Login required for {source.value.upper()} - please authenticate in browser",
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

        original_url = self._page.url
        original_page_count = len(self._tabs.context.pages)

        logger.info(f"Original URL: {original_url}")
        logger.info(f"Original page count: {original_page_count}")

        if not classifier.click_apply_button():
            return ApplicationResult(
                status=ApplicationStatus.NO_APPLY_BUTTON,
                message=f"Could not find Apply button on {source.value}",
                url=job_url
            )

        logger.info("Waiting for redirect to ATS...")
        redirected = self._wait_for_redirect(original_url, original_page_count)

        if not redirected:
            logger.warning("No redirect detected - may be on application page already")

        login_platform = self._check_login_required()
        if login_platform:
            return ApplicationResult(
                status=ApplicationStatus.NEEDS_LOGIN,
                message=f"Login required for {login_platform.upper()} ATS - please authenticate in browser",
                url=job_url,
            )

        dom_service = DomService(self._page)
        runner = ActionRunner(self._page, dom_service)

        logger.info(f"Now on: {self._page.url}")

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

        return processor.process(job_url, source=source)

    def _wait_for_redirect(self, original_url: str, original_page_count: int) -> bool:
        """Wait for navigation to complete after clicking apply."""
        start = time.time()
        timeout_sec = EXTERNAL_REDIRECT_TIMEOUT_MS / 1000

        while (time.time() - start) < timeout_sec:
            popup_url = self._tabs.get_captured_popup_url()
            if popup_url and popup_url != "about:blank":
                logger.info(f"Popup captured, navigating to: {popup_url}")
                try:
                    self._page.goto(popup_url)
                except Exception as e:
                    error_msg = str(e).lower()
                    if "err_aborted" in error_msg or "aborted" in error_msg:
                        logger.warning(f"Navigation aborted (SPA behavior): {e}")
                        self._page.wait(2000)
                    else:
                        raise
                self._page.wait(2000)
                self._tabs.close_extras(keep=1)
                return True

            current_url = self._page.url
            if current_url != original_url:
                logger.info(f"Same-tab navigation: {original_url} -> {current_url}")
                self._page.wait(2000)
                return True

            self._page.wait(500)

        logger.warning(f"Redirect timeout after {timeout_sec}s")
        return False

    def _check_login_required(self) -> Optional[str]:
        """Check if current page is a login page."""
        current_url = self._page.url.lower()

        for platform, patterns in LOGIN_URL_PATTERNS.items():
            if any(pattern in current_url for pattern in patterns):
                logger.warning(
                    f"[ACTION REQUIRED] {platform.upper()} login page detected: {current_url}"
                )
                return platform

        try:
            password_field = self._page.raw.locator('input[type="password"]').first
            if password_field.is_visible(timeout=1000):
                if "linkedin" in current_url:
                    platform = "linkedin"
                elif "indeed" in current_url:
                    platform = "indeed"
                elif "dice" in current_url:
                    platform = "dice"
                else:
                    platform = "unknown"

                logger.warning(
                    f"[ACTION REQUIRED] {platform.upper()} login form detected (password field visible)"
                )
                return platform
        except Exception:
            pass

        return None
