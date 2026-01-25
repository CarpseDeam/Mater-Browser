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

        Args:
            job_url: URL of the job posting (LinkedIn, Indeed, company site, etc.)

        Returns:
            ApplicationResult with status and details.
        """
        logger.info(f"Starting application: {job_url}")

        try:
            self._page = self._tabs.get_page()
            self._dom_service = DomService(self._page)
            self._runner = ActionRunner(self._page, self._dom_service)

            self._page.goto(job_url)
            self._page.wait(2000)

            if not self._click_apply_button():
                return ApplicationResult(
                    status=ApplicationStatus.NO_APPLY_BUTTON,
                    message="Could not find Apply button",
                    url=job_url
                )

            self._handle_new_tab()

            return self._process_form_pages(job_url)

        except Exception as e:
            logger.error(f"Application error: {e}")
            return ApplicationResult(
                status=ApplicationStatus.ERROR,
                message=str(e),
                url=job_url
            )

    def _click_apply_button(self) -> bool:
        """Find and click the Apply/Easy Apply button."""
        logger.info("Looking for Apply button...")

        apply_selectors = [
            'button.jobs-apply-button',
            'button[data-job-id]',
            'button#indeedApplyButton',
            'button[data-testid="indeedApplyButton"]',
            'button:has-text("Apply")',
            'a:has-text("Apply")',
            'button:has-text("Easy Apply")',
            'button:has-text("Apply Now")',
            'a:has-text("Apply Now")',
            '[data-automation="job-detail-apply"]',
            '.apply-button',
            '#apply-button',
        ]

        for selector in apply_selectors:
            try:
                loc = self._page.raw.locator(selector).first
                if loc.is_visible(timeout=1000):
                    logger.info(f"Found Apply button: {selector}")
                    loc.click()
                    self._page.wait(2000)
                    return True
            except Exception:
                continue

        logger.info("Trying DOM extraction to find Apply button...")
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
                            self._page.wait(2000)
                            logger.info(f"Clicked Apply via DOM: {el.ref}")
                            return True
                        except Exception:
                            continue

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
