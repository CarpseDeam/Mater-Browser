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


class ApplyPageType(Enum):
    """Classification of job application page type."""
    EASY_APPLY = "easy_apply"
    EXTERNAL_LINK = "external_link"
    ALREADY_APPLIED = "already_applied"
    CLOSED = "closed"
    LOGIN_REQUIRED = "login_required"
    UNKNOWN = "unknown"


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

    def _classify_page(self) -> ApplyPageType:
        """
        Classify the current page to determine application strategy.

        Checks in priority order:
        1. Already applied indicators
        2. Job closed indicators
        3. Login required
        4. Easy apply locators
        5. External link indicators
        6. Generic apply button
        7. Unknown (default)
        """
        page = self._page.raw

        # 1. Already applied check
        already_applied_phrases = [
            "already applied",
            "you applied",
            "you have applied",
            "application submitted",
            "previously applied",
        ]
        try:
            content_lower = page.content().lower()[:5000]
            if any(phrase in content_lower for phrase in already_applied_phrases):
                logger.debug("Page classification: ALREADY_APPLIED (phrase match)")
                return ApplyPageType.ALREADY_APPLIED
        except Exception:
            pass

        # 2. Job closed check
        closed_phrases = [
            "no longer accepting",
            "position filled",
            "position has been filled",
            "job has been filled",
            "no longer available",
            "this job is closed",
            "job is no longer",
            "posting has expired",
            "job expired",
        ]
        try:
            if any(phrase in content_lower for phrase in closed_phrases):
                logger.debug("Page classification: CLOSED (phrase match)")
                return ApplyPageType.CLOSED
        except Exception:
            pass

        # 3. Login required check
        if self._check_login_required():
            logger.debug("Page classification: LOGIN_REQUIRED")
            return ApplyPageType.LOGIN_REQUIRED

        # 4. Easy apply locators
        easy_apply_locator = (
            page.locator('[class*="easy-apply" i]')
            .or_(page.locator('[data-testid*="easyApply" i]'))
            .or_(page.locator('[data-testid*="easy-apply" i]'))
            .or_(page.locator('[aria-label*="Easy Apply" i]'))
            .or_(page.locator('.jobs-apply-button--top-card'))
            .or_(page.get_by_role("button", name=re.compile(r"easy\s*apply", re.IGNORECASE)))
        )
        try:
            if easy_apply_locator.first.is_visible(timeout=1000):
                logger.debug("Page classification: EASY_APPLY (locator match)")
                return ApplyPageType.EASY_APPLY
        except Exception:
            pass

        # 5. External link indicators
        external_link_locator = (
            page.locator('a[href*="greenhouse"]')
            .or_(page.locator('a[href*="lever.co"]'))
            .or_(page.locator('a[href*="workday"]'))
            .or_(page.locator('a[href*="myworkdayjobs"]'))
            .or_(page.locator('a[href*="icims"]'))
            .or_(page.locator('a[href*="smartrecruiters"]'))
            .or_(page.locator('a[href*="jobvite"]'))
            .or_(page.get_by_role("link", name=re.compile(r"apply on company", re.IGNORECASE)))
            .or_(page.get_by_role("link", name=re.compile(r"apply on employer", re.IGNORECASE)))
            .or_(page.get_by_text(re.compile(r"apply on company site", re.IGNORECASE)))
        )
        try:
            if external_link_locator.first.is_visible(timeout=1000):
                logger.debug("Page classification: EXTERNAL_LINK (locator match)")
                return ApplyPageType.EXTERNAL_LINK
        except Exception:
            pass

        # 6. Generic apply button visible
        generic_apply_locator = (
            page.get_by_role("button", name=re.compile(r"apply", re.IGNORECASE))
            .or_(page.get_by_role("link", name=re.compile(r"apply", re.IGNORECASE)))
            .or_(page.locator('[data-testid*="apply" i]'))
        )
        try:
            if generic_apply_locator.first.is_visible(timeout=1000):
                logger.debug("Page classification: EASY_APPLY (generic apply button)")
                return ApplyPageType.EASY_APPLY
        except Exception:
            pass

        # 7. Default
        logger.debug("Page classification: UNKNOWN")
        return ApplyPageType.UNKNOWN

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

        # Classify page to determine application strategy
        page_type = self._classify_page()
        logger.info(f"Page classification: {page_type.value}")

        if page_type == ApplyPageType.LOGIN_REQUIRED:
            return ApplicationResult(
                status=ApplicationStatus.NEEDS_LOGIN,
                message="Login required for LINKEDIN - please authenticate in browser",
                url=job_url,
            )

        if page_type == ApplyPageType.ALREADY_APPLIED:
            return ApplicationResult(
                status=ApplicationStatus.FAILED,
                message="Already applied to this job",
                url=job_url,
            )

        if page_type == ApplyPageType.CLOSED:
            return ApplicationResult(
                status=ApplicationStatus.FAILED,
                message="Job is closed or no longer accepting applications",
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

        # Classify page to determine application strategy
        page_type = self._classify_page()
        logger.info(f"Page classification: {page_type.value}")

        if page_type == ApplyPageType.LOGIN_REQUIRED:
            return ApplicationResult(
                status=ApplicationStatus.NEEDS_LOGIN,
                message=f"Login required for {source.value.upper()} - please authenticate in browser",
                url=job_url,
            )

        if page_type == ApplyPageType.ALREADY_APPLIED:
            return ApplicationResult(
                status=ApplicationStatus.FAILED,
                message="Already applied to this job",
                url=job_url,
            )

        if page_type == ApplyPageType.CLOSED:
            return ApplicationResult(
                status=ApplicationStatus.FAILED,
                message="Job is closed or no longer accepting applications",
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

        apply_locator = (
            # Primary: Role-based semantic locators (most resilient to HTML changes)
            page.get_by_role("button", name=re.compile(r"easy\s*apply|apply\s*now|apply", re.IGNORECASE))
            .or_(page.get_by_role("link", name=re.compile(r"easy\s*apply|apply\s*now|apply", re.IGNORECASE)))
            # Indeed external apply patterns (company website redirects)
            .or_(page.get_by_role("link", name=re.compile(r"apply on|apply at|company site", re.IGNORECASE)))
            .or_(page.locator('a[href*="apply"]'))
            .or_(page.locator('[data-testid="indeedApplyButton"]'))
            .or_(page.locator('[data-testid*="applyButton" i]'))
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
            first_match = apply_locator.first
            if first_match.is_visible(timeout=8000):
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
        self._log_available_buttons()
        return False

    def _log_available_buttons(self) -> None:
        """Log visible buttons/links on page for debugging apply button detection failures."""
        logger.debug("Available buttons/links on page:")
        try:
            buttons = self._page.raw.locator('button, a[href], [role="button"]').all()
            for i, btn in enumerate(buttons[:20]):
                try:
                    text = btn.text_content()[:50] if btn.text_content() else "(no text)"
                    tag = btn.evaluate("el => el.tagName")
                    logger.debug(f"  [{i}] <{tag}> {text}")
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"  Could not enumerate elements: {e}")

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

            # Try Indeed resume page handler FIRST (before DOM extraction)
            # This handles both selecting a resume AND clicking Continue
            if self._handle_indeed_resume_card():
                logger.info("Handled Indeed resume page - advancing to next step")
                self._page.wait(1500)
                if self._is_complete():
                    logger.info("Application complete after resume selection!")
                    return ApplicationResult(
                        status=ApplicationStatus.SUCCESS,
                        message="Application submitted successfully",
                        pages_processed=pages_processed,
                        url=job_url
                    )
                # _handle_indeed_resume_card already clicks Continue, so just continue loop
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
        Handle Indeed's resume selection page.

        Indeed shows resume options that must be selected. If a resume is already
        selected (has checkmark), we skip clicking and just advance to next step.

        Returns:
            True if on resume page and handled (either already selected or clicked),
            False if not on Indeed resume page.
        """
        page = self._page.raw
        current_url = self._page.url.lower()

        if "indeed.com" not in current_url:
            return False

        if "resume" not in current_url and "resume" not in page.content().lower()[:2000]:
            return False

        logger.info("Checking for Indeed resume selection page...")

        # FIRST: Check if any resume is already selected (has checkmark)
        selected_indicators = (
            page.locator('[data-testid*="selected" i]')
            .or_(page.locator('[aria-checked="true"]'))
            .or_(page.locator('[aria-selected="true"]'))
            .or_(page.locator('[data-selected="true"]'))
            .or_(page.locator('.ia-Resume-selectedIcon'))
            .or_(page.locator('[class*="selected"][class*="resume" i]'))
            .or_(page.locator('[class*="resume"][class*="selected" i]'))
            .or_(page.locator('.ia-Resume svg[class*="check" i]'))
            .or_(page.locator('[class*="resume-card"] svg'))
        )

        try:
            if selected_indicators.first.is_visible(timeout=2000):
                logger.info("Resume already selected (found selection indicator) - skipping card click")
                return self._click_indeed_continue()
        except Exception as e:
            logger.debug(f"No selection indicator found: {e}")

        # No resume selected - try to click "Use your Indeed Resume" card
        logger.info("No resume selected - looking for Indeed resume card to click...")

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

                return self._click_indeed_continue()

        except Exception as e:
            logger.debug(f"Indeed resume card not found: {e}")

        return False

    def _click_indeed_continue(self) -> bool:
        """
        Click Indeed's Continue/Next button on resume page.

        Indeed SmartApply uses specific button patterns. May need to scroll
        to make button visible.

        Returns:
            True if Continue button found and clicked, False otherwise.
        """
        page = self._page.raw

        logger.info("Looking for Indeed Continue button...")

        indeed_continue_locator = (
            page.locator('[data-testid="ia-continueButton"]')
            .or_(page.locator('[data-testid*="continue" i]'))
            .or_(page.locator('[data-tn-element="continueButton"]'))
            .or_(page.get_by_role("button", name=re.compile(r"^continue$", re.IGNORECASE)))
            .or_(page.get_by_role("button", name=re.compile(r"continue to", re.IGNORECASE)))
            .or_(page.locator('.ia-continueButton'))
            .or_(page.locator('[class*="ia-"][class*="continue" i]'))
            .or_(page.locator('[class*="continue"][class*="button" i]'))
            .or_(page.locator('button:has-text("Continue")'))
            .or_(page.locator('[type="submit"]'))
        )

        try:
            first_match = indeed_continue_locator.first
            if first_match.is_visible(timeout=2000):
                try:
                    text = first_match.evaluate("el => el.textContent?.trim()?.substring(0, 30)")
                    logger.info(f"Found Indeed Continue button: '{text}'")
                except Exception:
                    pass

                first_match.click()
                logger.info("Clicked Indeed Continue button successfully")
                self._page.wait(1500)
                return True
        except Exception as e:
            logger.debug(f"Continue button not immediately visible: {e}")

        # Scroll down and try again
        logger.info("Scrolling to find Continue button...")
        try:
            page.evaluate("window.scrollBy(0, 500)")
            self._page.wait(500)

            first_match = indeed_continue_locator.first
            if first_match.is_visible(timeout=2000):
                first_match.scroll_into_view_if_needed()
                first_match.click()
                logger.info("Clicked Indeed Continue button after scroll")
                self._page.wait(1500)
                return True
        except Exception as e:
            logger.debug(f"Continue button not found after scroll: {e}")

        logger.info("Falling back to generic next button handler...")
        return self._click_next_button()

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
