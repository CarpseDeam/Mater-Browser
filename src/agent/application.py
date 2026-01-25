"""Job application agent - orchestrates the full application flow."""
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..browser.page import Page
from ..browser.tabs import TabManager
from ..extractor.dom_service import DomService, DomState
from .claude import ClaudeAgent
from .actions import ActionPlan
from ..executor.runner import ActionRunner

logger = logging.getLogger(__name__)

APPLICATION_TIMEOUT_SECONDS: float = 180.0


class JobSource(Enum):
    """Source platform for job listing."""
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    DICE = "dice"
    DIRECT = "direct"


# URL patterns for source detection
LINKEDIN_PATTERNS: list[str] = ["linkedin.com/jobs", "linkedin.com/job"]
INDEED_PATTERNS: list[str] = ["indeed.com/viewjob", "indeed.com/jobs", "indeed.com/rc"]
DICE_PATTERNS: list[str] = ["dice.com/job-detail", "dice.com/jobs"]

# Apply button selectors by source
LINKEDIN_APPLY_SELECTORS: list[str] = [
    'button.jobs-apply-button',
    'button[aria-label*="Easy Apply"]',
    'button:has-text("Easy Apply")',
]

EXTERNAL_APPLY_SELECTORS: list[str] = [
    # Indeed
    'button#indeedApplyButton',
    'button[data-testid="indeedApplyButton"]',
    'a[data-testid="indeedApplyButton"]',
    'button[id*="apply"]',
    # Dice
    'a.apply-button',
    'button.btn-apply',
    # Generic
    'button:has-text("Apply")',
    'a:has-text("Apply")',
    'button:has-text("Apply Now")',
    'a:has-text("Apply Now")',
    'a:has-text("Apply on company site")',
    '[data-automation="job-detail-apply"]',
]

# Navigation timeout for external redirects (milliseconds)
EXTERNAL_REDIRECT_TIMEOUT_MS: int = 15000


class ApplicationStatus(Enum):
    """Status of job application attempt."""
    SUCCESS = "success"
    FAILED = "failed"
    NO_APPLY_BUTTON = "no_apply_button"
    MAX_PAGES_REACHED = "max_pages_reached"
    STUCK = "stuck"
    ERROR = "error"


@dataclass
class ApplicationResult:
    """Result of a job application attempt."""
    status: ApplicationStatus
    message: str
    pages_processed: int = 0
    url: str = ""


class ApplicationAgent:
    """
    Orchestrates complete job application flow.

    Handles:
    - Finding and clicking Apply button
    - Following external ATS links (new tabs)
    - Multi-page form navigation
    - Resume upload
    - Submit detection
    """

    def __init__(
        self,
        tab_manager: TabManager,
        profile: dict,
        resume_path: Optional[str] = None,
        max_pages: int = 15,
        claude_model: str = "claude-sonnet-4-20250514",
        timeout_seconds: float = APPLICATION_TIMEOUT_SECONDS,
    ) -> None:
        """
        Initialize the application agent.

        Args:
            tab_manager: TabManager for handling browser tabs.
            profile: User profile dictionary with application data.
            resume_path: Optional path to resume PDF file.
            max_pages: Maximum pages to process before giving up.
            claude_model: Claude model to use for form analysis.
            timeout_seconds: Maximum seconds for entire application attempt.
        """
        self._tabs = tab_manager
        self._profile = profile
        self._resume_path = resume_path
        self._max_pages = max_pages
        self._timeout_seconds = timeout_seconds
        self._claude = ClaudeAgent(model=claude_model)

        self._page: Optional[Page] = None
        self._dom_service: Optional[DomService] = None
        self._runner: Optional[ActionRunner] = None

    def apply(self, job_url: str) -> ApplicationResult:
        """
        Apply to a job given its URL.

        Routes to source-specific apply logic based on URL.

        Args:
            job_url: URL of the job posting (LinkedIn, Indeed, company site, etc.)

        Returns:
            ApplicationResult with status and details.
        """
        logger.info(f"Starting application: {job_url}")

        source = self._detect_source(job_url)
        logger.info(f"Detected source: {source.value}")

        try:
            self._page = self._tabs.get_page()
            self._dom_service = DomService(self._page)
            self._runner = ActionRunner(self._page, self._dom_service)

            if source == JobSource.LINKEDIN:
                return self._apply_linkedin(job_url)
            else:
                return self._apply_external(job_url, source)

        except Exception as e:
            logger.exception(f"Application error: {e}")
            return ApplicationResult(
                status=ApplicationStatus.ERROR,
                message=str(e),
                url=job_url
            )

    def _detect_source(self, url: str) -> JobSource:
        """
        Detect job source platform from URL.

        Args:
            url: Job posting URL.

        Returns:
            JobSource enum value for the detected platform.
        """
        url_lower = url.lower()

        if any(pattern in url_lower for pattern in LINKEDIN_PATTERNS):
            return JobSource.LINKEDIN
        elif any(pattern in url_lower for pattern in INDEED_PATTERNS):
            return JobSource.INDEED
        elif any(pattern in url_lower for pattern in DICE_PATTERNS):
            return JobSource.DICE
        else:
            return JobSource.DIRECT

    def _apply_linkedin(self, job_url: str) -> ApplicationResult:
        """
        Handle LinkedIn Easy Apply flow.

        Easy Apply opens a modal on the same page - no navigation required.
        LinkedIn uses SPA routing which can cause ERR_ABORTED on goto().

        Args:
            job_url: LinkedIn job posting URL.

        Returns:
            ApplicationResult with status and details.
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

        # Find and click Easy Apply button
        if not self._click_apply_button(LINKEDIN_APPLY_SELECTORS):
            # Fallback to generic selectors
            if not self._click_apply_button(EXTERNAL_APPLY_SELECTORS):
                return ApplicationResult(
                    status=ApplicationStatus.NO_APPLY_BUTTON,
                    message="Could not find Easy Apply button",
                    url=job_url
                )

        # Wait for modal to appear
        self._page.wait(1500)

        # Modal is on same page - process forms
        return self._process_form_pages(job_url)

    def _apply_external(self, job_url: str, source: JobSource) -> ApplicationResult:
        """
        Handle external job board apply flow (Indeed, Dice, etc).

        External applies redirect to an ATS (Greenhouse, Lever, Workday).
        We must wait for the redirect BEFORE extracting DOM.

        Args:
            job_url: Job posting URL.
            source: Detected job source platform.

        Returns:
            ApplicationResult with status and details.
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

        # Capture current state before clicking
        original_url = self._page.url
        original_page_count = len(self._tabs.context.pages)

        logger.info(f"Original URL: {original_url}")
        logger.info(f"Original page count: {original_page_count}")

        # Find and click apply button
        if not self._click_apply_button(EXTERNAL_APPLY_SELECTORS):
            return ApplicationResult(
                status=ApplicationStatus.NO_APPLY_BUTTON,
                message=f"Could not find Apply button on {source.value}",
                url=job_url
            )

        # Wait for either: new tab opens OR current page navigates
        logger.info("Waiting for redirect to ATS...")
        redirected = self._wait_for_redirect(original_url, original_page_count)

        if not redirected:
            logger.warning("No redirect detected - may be on application page already")

        # Reinitialize DOM service for new page context
        self._dom_service = DomService(self._page)
        self._runner = ActionRunner(self._page, self._dom_service)

        logger.info(f"Now on: {self._page.url}")

        # NOW we can process the actual application form
        return self._process_form_pages(job_url)

    def _wait_for_redirect(self, original_url: str, original_page_count: int) -> bool:
        """
        Wait for navigation to complete after clicking apply.

        Handles both:
        - Same-tab navigation (URL changes)
        - New-tab opens (page count increases)

        Args:
            original_url: URL before clicking apply.
            original_page_count: Number of open tabs before clicking.

        Returns:
            True if redirect detected, False if timeout.
        """
        start = time.time()
        timeout_sec = EXTERNAL_REDIRECT_TIMEOUT_MS / 1000

        while (time.time() - start) < timeout_sec:
            # Check for new tab
            current_pages = self._tabs.context.pages
            if len(current_pages) > original_page_count:
                # Switch to new tab
                new_page = current_pages[-1]
                self._page = Page(new_page)
                logger.info(f"Switched to new tab: {self._page.url}")
                self._page.wait(2000)
                return True

            # Check for same-tab navigation
            current_url = self._page.url
            if current_url != original_url:
                logger.info(f"Same-tab navigation: {original_url} -> {current_url}")
                self._page.wait(2000)
                return True

            # Small wait before next check
            self._page.wait(500)

        logger.warning(f"Redirect timeout after {timeout_sec}s")
        return False

    def _click_apply_button(self, selectors: list[str]) -> bool:
        """
        Find and click apply button using provided selectors.

        Args:
            selectors: List of CSS/text selectors to try in order.

        Returns:
            True if button found and clicked, False otherwise.
        """
        logger.info(f"Looking for Apply button ({len(selectors)} selectors)...")

        # Try explicit selectors first
        for selector in selectors:
            try:
                loc = self._page.raw.locator(selector).first
                if loc.is_visible(timeout=1000):
                    logger.info(f"Found Apply button: {selector}")
                    loc.click()
                    return True
            except Exception:
                continue

        # Fallback: DOM extraction search
        logger.info("Trying DOM extraction to find Apply button...")
        try:
            dom_state = self._dom_service.extract()

            for el in dom_state.elements:
                text = (el.text or "").lower()
                label = (el.label or "").lower()
                btn_text = (el.buttonText or "").lower()

                if any(kw in text or kw in label or kw in btn_text
                       for kw in ["apply", "easy apply", "apply now"]):
                    if el.tag in ("button", "a") or el.type in ("submit", "button"):
                        selector = self._dom_service.get_selector(el.ref)
                        if selector:
                            try:
                                self._page.raw.locator(selector).first.click()
                                logger.info(f"Clicked Apply via DOM: {el.ref}")
                                return True
                            except Exception:
                                continue
        except Exception as e:
            logger.warning(f"DOM extraction failed: {e}")

        return False

    def _handle_new_tab(self) -> None:
        """Check for and switch to new tab (external ATS)."""
        pages = self._tabs.context.pages

        if len(pages) > 1:
            new_page = pages[-1]
            self._page = Page(new_page)
            self._dom_service = DomService(self._page)
            self._runner = ActionRunner(self._page, self._dom_service)
            logger.info(f"Switched to new tab: {self._page.url}")
            self._page.wait(2000)

    def _process_form_pages(self, job_url: str) -> ApplicationResult:
        """Process multi-page application form."""
        pages_processed = 0
        stuck_count = 0
        last_url = ""
        start_time = time.time()

        while pages_processed < self._max_pages:
            elapsed = time.time() - start_time
            if elapsed > self._timeout_seconds:
                logger.warning(f"Application timed out after {elapsed:.1f}s")
                return ApplicationResult(
                    status=ApplicationStatus.STUCK,
                    message=f"Timed out after {elapsed:.1f}s",
                    pages_processed=pages_processed,
                    url=job_url,
                )
            pages_processed += 1
            current_url = self._page.url

            logger.info(f"=== Page {pages_processed} ===")
            logger.info(f"URL: {current_url}")

            if self._is_complete():
                logger.info("Application complete!")
                return ApplicationResult(
                    status=ApplicationStatus.SUCCESS,
                    message="Application submitted successfully",
                    pages_processed=pages_processed,
                    url=job_url
                )

            dom_state = self._dom_service.extract()
            logger.info(f"Found {dom_state.elementCount} elements")

            if dom_state.elementCount == 0:
                stuck_count += 1
                if stuck_count >= 3:
                    return ApplicationResult(
                        status=ApplicationStatus.STUCK,
                        message="No interactive elements found",
                        pages_processed=pages_processed,
                        url=job_url
                    )
                self._page.wait(2000)
                continue

            plan = self._claude.analyze_form(
                dom_state,
                self._profile,
                self._dom_service
            )

            if not plan:
                logger.error("Failed to get action plan")
                stuck_count += 1
                if stuck_count >= 3:
                    return ApplicationResult(
                        status=ApplicationStatus.STUCK,
                        message="Failed to analyze form",
                        pages_processed=pages_processed,
                        url=job_url
                    )
                continue

            self._try_resume_upload(dom_state)

            logger.info(f"Executing plan: {plan.reasoning}")
            success = self._runner.execute(plan)

            if not success:
                logger.warning("Plan execution had errors")

            self._page.wait(1500)

            self._handle_new_tab()

            new_url = self._page.url
            if new_url == last_url and new_url == current_url:
                if not self._click_next_button():
                    stuck_count += 1
                    if stuck_count >= 3:
                        return ApplicationResult(
                            status=ApplicationStatus.STUCK,
                            message="Could not advance to next page",
                            pages_processed=pages_processed,
                            url=job_url
                        )
            else:
                stuck_count = 0

            last_url = current_url

        return ApplicationResult(
            status=ApplicationStatus.MAX_PAGES_REACHED,
            message=f"Reached max pages ({self._max_pages})",
            pages_processed=pages_processed,
            url=job_url
        )

    def _try_resume_upload(self, dom_state: DomState) -> bool:
        """Try to upload resume if file input found."""
        if not self._resume_path:
            return False

        for el in dom_state.elements:
            if el.tag == "input" and el.type == "file":
                label = (el.label or "").lower()
                name = (el.name or "").lower()

                if any(kw in label or kw in name
                       for kw in ["resume", "cv", "upload"]):
                    selector = self._dom_service.get_selector(el.ref)
                    if selector:
                        try:
                            self._page.raw.locator(selector).set_input_files(
                                self._resume_path
                            )
                            logger.info(f"Uploaded resume to {el.ref}")
                            self._page.wait(1000)
                            return True
                        except Exception as e:
                            logger.warning(f"Resume upload failed: {e}")

        return False

    def _click_next_button(self) -> bool:
        """Try to click Next/Continue/Submit button."""
        next_selectors = [
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button:has-text("Review")',
            'button:has-text("Submit")',
            'button[type="submit"]',
            'input[type="submit"]',
            'button[aria-label*="Continue"]',
            'button[aria-label*="Next"]',
        ]

        for selector in next_selectors:
            try:
                loc = self._page.raw.locator(selector).first
                if loc.is_visible(timeout=500):
                    loc.click()
                    self._page.wait(1500)
                    logger.info(f"Clicked next button: {selector}")
                    return True
            except Exception:
                continue

        return False

    def _is_complete(self) -> bool:
        """Check if application was submitted."""
        completion_indicators = [
            'text="Application submitted"',
            'text="Thank you"',
            'text="application has been submitted"',
            'text="successfully submitted"',
            'text="Application received"',
            '[data-test="application-complete"]',
            '.application-complete',
            '#application-success',
        ]

        for indicator in completion_indicators:
            try:
                if self._page.raw.locator(indicator).first.is_visible(timeout=500):
                    return True
            except Exception:
                continue

        try:
            content = self._page.raw.content().lower()
            if any(phrase in content for phrase in [
                "thank you for applying",
                "application submitted",
                "application received",
                "we have received your application",
            ]):
                return True
        except Exception:
            pass

        return False
