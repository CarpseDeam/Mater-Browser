"""Job application agent - orchestrates the full application flow."""
import logging
import re
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
# DICE disabled - not currently scraping
# DICE_PATTERNS: list[str] = ["dice.com/job-detail", "dice.com/jobs"]

# Navigation timeout for external redirects (milliseconds)
EXTERNAL_REDIRECT_TIMEOUT_MS: int = 15000

# Login page URL patterns by platform
LOGIN_URL_PATTERNS: dict[str, list[str]] = {
    "linkedin": [
        "linkedin.com/login",
        "linkedin.com/checkpoint",
        "linkedin.com/uas/login",
    ],
    "indeed": [
        "secure.indeed.com/auth",
        "indeed.com/account/login",
        "indeed.com/account/signin",
    ],
    # Dice disabled
    # "dice": [
    #     "dice.com/dashboard/login",
    #     "dice.com/login",
    # ],
    "generic": [
        "/login",
        "/signin",
        "/sign-in",
        "/auth",
        "/authenticate",
    ],
}


class ApplicationStatus(Enum):
    """Status of job application attempt."""
    SUCCESS = "success"
    FAILED = "failed"
    NO_APPLY_BUTTON = "no_apply_button"
    MAX_PAGES_REACHED = "max_pages_reached"
    STUCK = "stuck"
    ERROR = "error"
    NEEDS_LOGIN = "needs_login"


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
        # Dice disabled
        # elif any(pattern in url_lower for pattern in DICE_PATTERNS):
        #     return JobSource.DICE
        else:
            return JobSource.DIRECT

    def _check_login_required(self) -> Optional[str]:
        """
        Check if current page is a login page.

        Returns:
            Platform name if login required, None if not on login page.
        """
        current_url = self._page.url.lower()

        # Check URL patterns
        for platform, patterns in LOGIN_URL_PATTERNS.items():
            if any(pattern in current_url for pattern in patterns):
                logger.warning(
                    f"[ACTION REQUIRED] {platform.upper()} login page detected: {current_url}"
                )
                return platform

        # Check page content for login indicators
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

        # Check if we hit a login wall
        login_platform = self._check_login_required()
        if login_platform:
            return ApplicationResult(
                status=ApplicationStatus.NEEDS_LOGIN,
                message=f"Login required for {login_platform.upper()} - please authenticate in browser",
                url=job_url,
            )

        # Find and click Easy Apply button
        if not self._click_apply_button():
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

        # Check if we hit a login wall immediately
        login_platform = self._check_login_required()
        if login_platform:
            return ApplicationResult(
                status=ApplicationStatus.NEEDS_LOGIN,
                message=f"Login required for {login_platform.upper()} - please authenticate in browser",
                url=job_url,
            )

        # Capture current state before clicking
        original_url = self._page.url
        original_page_count = len(self._tabs.context.pages)

        logger.info(f"Original URL: {original_url}")
        logger.info(f"Original page count: {original_page_count}")

        # Find and click apply button
        if not self._click_apply_button():
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

        # Check if redirect landed on a login page
        login_platform = self._check_login_required()
        if login_platform:
            return ApplicationResult(
                status=ApplicationStatus.NEEDS_LOGIN,
                message=f"Login required for {login_platform.upper()} ATS - please authenticate in browser",
                url=job_url,
            )

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

    def _click_apply_button(self) -> bool:
        """
        Find and click the Apply button using semantic locators.

        Uses Playwright's combined locator pattern for resilience:
        1. Role-based (button/link with "apply" text) - most resilient
        2. Attribute-based (data-testid, aria-label) - platform-specific fallback
        3. Text content fallback - last resort

        Returns:
            True if button found and clicked, False otherwise.
        """
        logger.info("Looking for Apply button (semantic locator)...")

        page = self._page.raw

        # Combined locator - checks all strategies in parallel, not sequential
        # The .or_() method combines locators into one that matches ANY of them
        apply_locator = (
            # Primary: Role-based semantic locators (most resilient to HTML changes)
            page.get_by_role("button", name=re.compile(r"easy\s*apply|apply\s*now|apply", re.IGNORECASE))
            .or_(page.get_by_role("link", name=re.compile(r"easy\s*apply|apply\s*now|apply", re.IGNORECASE)))
            # Secondary: Attribute-based (platform-specific)
            .or_(page.locator('[data-testid*="apply" i]'))
            .or_(page.locator('[aria-label*="apply" i]'))
            .or_(page.locator('[id*="apply" i][id*="button" i]'))
            # Tertiary: Class-based (less stable but common)
            .or_(page.locator('.jobs-apply-button'))
            .or_(page.locator('.apply-button'))
            .or_(page.locator('[class*="apply"][class*="button" i]'))
        )

        try:
            # Single visibility check with reasonable timeout
            first_match = apply_locator.first
            if first_match.is_visible(timeout=5000):
                # Log what we're clicking for debugging
                try:
                    tag = first_match.evaluate("el => el.tagName")
                    text = first_match.evaluate("el => el.textContent?.trim()?.substring(0, 50)")
                    logger.info(f"Found Apply button: <{tag}> '{text}'")
                except Exception:
                    logger.info("Found Apply button (details unavailable)")

                first_match.click()
                logger.info("Clicked Apply button successfully")
                return True

        except Exception as e:
            logger.debug(f"Combined locator failed: {e}")

        # Last resort: Text content search (handles weird markup)
        logger.info("Trying text content fallback...")
        try:
            # Look for any clickable element containing "apply"
            text_locator = page.locator('button, a, [role="button"]').filter(
                has_text=re.compile(r"apply", re.IGNORECASE)
            )

            if text_locator.first.is_visible(timeout=2000):
                text_locator.first.click()
                logger.info("Clicked Apply via text content fallback")
                return True

        except Exception as e:
            logger.debug(f"Text fallback failed: {e}")

        logger.warning("Could not find Apply button with any strategy")
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

            # Try Indeed resume card FIRST (before DOM extraction)
            if self._handle_indeed_resume_card():
                logger.info("Handled Indeed resume card - continuing to next page check")
                self._page.wait(1500)
                if self._is_complete():
                    logger.info("Application complete after resume selection!")
                    return ApplicationResult(
                        status=ApplicationStatus.SUCCESS,
                        message="Application submitted successfully",
                        pages_processed=pages_processed,
                        url=job_url
                    )
                self._click_next_button()
                self._page.wait(1500)
                continue

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

    def _handle_indeed_resume_card(self) -> bool:
        """
        Handle Indeed's pre-uploaded resume selection.

        Indeed shows a "Use your Indeed Resume" card that must be clicked,
        rather than a traditional file upload input.

        Returns:
            True if resume card found and clicked, False otherwise.
        """
        page = self._page.raw
        current_url = self._page.url.lower()

        if "indeed.com" not in current_url:
            return False

        logger.info("Checking for Indeed resume card...")

        resume_card_locator = (
            page.get_by_text(re.compile(r"use your indeed resume", re.IGNORECASE))
            .or_(page.get_by_text(re.compile(r"use indeed resume", re.IGNORECASE)))
            .or_(page.get_by_role("button", name=re.compile(r"indeed resume", re.IGNORECASE)))
            .or_(page.get_by_role("radio", name=re.compile(r"indeed resume", re.IGNORECASE)))
            .or_(page.locator('[data-testid*="resume-card" i]'))
            .or_(page.locator('[data-testid*="indeed-resume" i]'))
            .or_(page.locator('[class*="resume"][class*="card" i]'))
            .or_(page.locator('[class*="resume-display-card" i]'))
            .or_(page.locator('[aria-label*="Indeed Resume" i]'))
        )

        try:
            first_match = resume_card_locator.first
            if first_match.is_visible(timeout=3000):
                try:
                    tag = first_match.evaluate("el => el.tagName")
                    text = first_match.evaluate("el => el.textContent?.trim()?.substring(0, 50)")
                    logger.info(f"Found Indeed resume card: <{tag}> '{text}'")
                except Exception:
                    logger.info("Found Indeed resume card (details unavailable)")

                first_match.click()
                logger.info("Clicked Indeed resume card successfully")
                self._page.wait(1000)
                return True

        except Exception as e:
            logger.debug(f"Indeed resume card not found: {e}")

        return False

    def _click_next_button(self) -> bool:
        """
        Try to click Next/Continue/Submit button using semantic locators.

        Uses Playwright's combined locator pattern for resilience and speed.

        Returns:
            True if button found and clicked, False otherwise.
        """
        page = self._page.raw

        # Combined locator - checks all strategies in parallel
        next_locator = (
            # Primary: Role-based semantic locators
            page.get_by_role("button", name=re.compile(r"next|continue|submit|review", re.IGNORECASE))
            .or_(page.get_by_role("link", name=re.compile(r"next|continue", re.IGNORECASE)))
            # Secondary: Attribute-based
            .or_(page.locator('[type="submit"]'))
            .or_(page.locator('[aria-label*="Next" i]'))
            .or_(page.locator('[aria-label*="Continue" i]'))
            .or_(page.locator('[aria-label*="Submit" i]'))
            # Tertiary: Data attributes (common in React apps)
            .or_(page.locator('[data-testid*="next" i]'))
            .or_(page.locator('[data-testid*="submit" i]'))
        )

        try:
            first_match = next_locator.first
            if first_match.is_visible(timeout=3000):
                try:
                    tag = first_match.evaluate("el => el.tagName")
                    text = first_match.evaluate("el => el.textContent?.trim()?.substring(0, 30)")
                    logger.info(f"Found Next button: <{tag}> '{text}'")
                except Exception:
                    logger.info("Found Next button (details unavailable)")

                first_match.click()
                self._page.wait(1500)
                logger.info("Clicked Next button successfully")
                return True

        except Exception as e:
            logger.debug(f"Next button locator failed: {e}")

        return False

    def _is_complete(self) -> bool:
        """
        Check if application was submitted using semantic locators.

        Returns:
            True if completion indicators found, False otherwise.
        """
        page = self._page.raw

        # Combined locator for completion indicators
        completion_locator = (
            # Text-based indicators
            page.get_by_text(re.compile(r"application submitted|thank you|successfully submitted|application received", re.IGNORECASE))
            # Data attributes
            .or_(page.locator('[data-test="application-complete"]'))
            .or_(page.locator('[data-testid*="success" i]'))
            .or_(page.locator('[data-testid*="complete" i]'))
            # Class/ID based
            .or_(page.locator('.application-complete'))
            .or_(page.locator('#application-success'))
            .or_(page.locator('[class*="success"][class*="message" i]'))
        )

        try:
            if completion_locator.first.is_visible(timeout=1000):
                logger.info("Completion indicator found via locator")
                return True
        except Exception:
            pass

        # Fallback: Check page content for completion phrases
        try:
            content = page.content().lower()
            completion_phrases = [
                "thank you for applying",
                "application submitted",
                "application received",
                "we have received your application",
                "your application has been submitted",
            ]
            if any(phrase in content for phrase in completion_phrases):
                logger.info("Completion detected via page content")
                return True
        except Exception:
            pass

        return False
