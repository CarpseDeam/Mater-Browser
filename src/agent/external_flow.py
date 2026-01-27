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
    MEDIUM_WAIT_MS,
    LONG_WAIT_MS,
    PAGE_LOAD_TIMEOUT_MS,
    SHORT_WAIT_MS,
)
from .form_processor import FormProcessor
from .answer_engine import AnswerEngine
from .indeed_form_filler import IndeedFormFiller
from .indeed_helpers import IndeedHelpers

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

        if not self._page.goto(job_url):
            return ApplicationResult(
                status=ApplicationStatus.ERROR,
                message="Navigation failed completely",
                url=job_url,
            )

        self._page.wait(LONG_WAIT_MS)

        try:
            self._page.raw.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
        except Exception:
            pass

        # Check for external-only job FIRST (Indeed "Apply on company site")
        if self._is_external_only_job():
            logger.info("External-only job detected - skipping (Easy Apply only)")
            return ApplicationResult(
                status=ApplicationStatus.SKIPPED,
                message="External application - Easy Apply only",
                url=job_url,
            )

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

        # Use deterministic filler for Indeed Easy Apply
        if self._is_indeed_easy_apply():
            return self._process_indeed_easy_apply(job_url)

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

    def _is_external_only_job(self) -> bool:
        """Check if job page only has external apply (no Easy Apply)."""
        try:
            # Indeed: "Apply on company site" button
            external_selectors = [
                'button:has-text("Apply on company site")',
                'a:has-text("Apply on company site")',
                '[data-testid="indeedApply-button"]:has-text("company site")',
                'button[aria-label*="Apply on company"]',
            ]
            for selector in external_selectors:
                if self._page.raw.locator(selector).first.is_visible(timeout=1000):
                    logger.info(f"Found external-only button: {selector}")
                    return True
        except Exception:
            pass
        return False

    def _is_indeed_easy_apply(self) -> bool:
        """Check if current page is Indeed Easy Apply flow."""
        url = self._page.url.lower()
        return "smartapply.indeed.com" in url or "indeedapply" in url

    def _process_indeed_easy_apply(self, job_url: str) -> ApplicationResult:
        """Process Indeed Easy Apply using deterministic form filler."""
        logger.info("Using deterministic form filler for Indeed Easy Apply")

        answer_engine = AnswerEngine()
        filler = IndeedFormFiller(self._page.raw, answer_engine)
        helpers = IndeedHelpers(self._page)

        for page_num in range(self._max_pages):
            self._page.wait(1000)

            # Check for success
            if filler.is_success_page():
                return ApplicationResult(
                    status=ApplicationStatus.SUCCESS,
                    message="Application submitted",
                    pages=page_num + 1,
                    url=job_url,
                )

            # Handle resume selection page
            if filler.is_resume_page():
                helpers.handle_resume_card()
                self._page.wait(1000)
                continue

            # Fill form fields
            success, unknown = filler.fill_current_page()

            if unknown:
                logger.warning(f"Skipping job - unknown questions: {unknown[:3]}")
                return ApplicationResult(
                    status=ApplicationStatus.FAILED,
                    message=f"Unknown questions: {', '.join(unknown[:3])}",
                    pages=page_num + 1,
                    url=job_url,
                )

            # Handle modals
            helpers.dismiss_modal()

            # Click continue
            if not filler.click_continue():
                logger.warning("Could not find continue button")
                break

            self._page.wait(1000)

        return ApplicationResult(
            status=ApplicationStatus.FAILED,
            message="Max pages reached or stuck",
            pages=self._max_pages,
            url=job_url,
        )

    def _wait_for_redirect(self, original_url: str, original_page_count: int) -> bool:
        """Wait for navigation to complete after clicking apply."""
        start = time.time()
        timeout_sec = EXTERNAL_REDIRECT_TIMEOUT_MS / 1000

        while (time.time() - start) < timeout_sec:
            if self._handle_popup_redirect():
                return True
            if self._check_same_tab_redirect(original_url):
                return True
            self._page.wait(SHORT_WAIT_MS)

        logger.warning(f"Redirect timeout after {timeout_sec}s")
        return False

    def _handle_popup_redirect(self) -> bool:
        """Check for and handle popup redirect. Returns True if popup found."""
        popup_url = self._tabs.get_captured_popup_url()
        if not popup_url or popup_url == "about:blank":
            return False
        logger.info(f"Popup captured, navigating to: {popup_url}")
        self._page.goto(popup_url)
        self._page.wait(LONG_WAIT_MS)
        self._tabs.close_extras(keep=1)
        return True

    def _check_same_tab_redirect(self, original_url: str) -> bool:
        """Check for same-tab navigation. Returns True if redirected."""
        current_url = self._page.url
        if current_url != original_url:
            logger.info(f"Same-tab navigation: {original_url} -> {current_url}")
            self._page.wait(LONG_WAIT_MS)
            return True
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
