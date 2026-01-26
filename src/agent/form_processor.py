"""Form processing logic for multi-page application flows."""
import logging
import re
import time
from typing import Optional

from ..browser.page import Page
from ..browser.tabs import TabManager
from ..extractor.dom_service import DomService
from .claude import ClaudeAgent
from .actions import ActionPlan
from ..executor.runner import ActionRunner
from .page_classifier import PageClassifier
from .models import (
    JobSource,
    ApplicationStatus,
    ApplicationResult,
    ACCOUNT_CREATION_URL_PATTERNS,
    ACCOUNT_CREATION_CONTENT,
    LOOP_DETECTION_THRESHOLD,
    LOOP_ELEMENT_COUNT_TOLERANCE,
)
from .indeed_helpers import IndeedHelpers

logger = logging.getLogger(__name__)


class FormProcessor:
    """Processes multi-page application forms."""

    def __init__(
        self,
        page: Page,
        dom_service: DomService,
        claude: ClaudeAgent,
        runner: ActionRunner,
        tabs: TabManager,
        profile: dict,
        resume_path: Optional[str],
        timeout_seconds: float,
        max_pages: int,
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
        self._page_states: list[tuple[str, int]] = []
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
                return ApplicationResult(
                    status=ApplicationStatus.STUCK,
                    message=f"Timed out after {elapsed:.1f}s",
                    pages_processed=pages_processed,
                    url=job_url,
                )
            pages_processed += 1

            if source == JobSource.INDEED and self._indeed_helpers.dismiss_modal():
                logger.info("Dismissed Indeed modal, continuing...")
                pages_processed -= 1
                continue

            current_url = self._page.url

            classifier = PageClassifier(self._page.raw)
            if classifier._is_payment_page():
                logger.warning(f"PAYMENT PAGE DETECTED during form flow - aborting: {current_url}")
                return ApplicationResult(
                    status=ApplicationStatus.FAILED,
                    message="Payment page detected during application - safety abort",
                    pages_processed=pages_processed,
                    url=job_url,
                )

            try:
                page_text = self._page.raw.content()[:5000]
            except Exception:
                page_text = ""

            if self._is_account_creation_page(current_url, page_text):
                logger.warning(f"ACCOUNT CREATION PAGE DETECTED - aborting: {current_url}")
                return ApplicationResult(
                    status=ApplicationStatus.FAILED,
                    message="Requires account creation",
                    pages_processed=pages_processed,
                    url=job_url,
                )

            logger.info(f"=== Page {pages_processed} ===")
            logger.info(f"URL: {current_url}")

            if self._is_complete(pages_processed):
                logger.info("Application complete!")
                return ApplicationResult(
                    status=ApplicationStatus.SUCCESS,
                    message="Application submitted successfully",
                    pages_processed=pages_processed,
                    url=job_url
                )

            if self._indeed_helpers.handle_resume_card():
                logger.info("Handled Indeed resume page - advancing to next step")
                self._page.wait(1500)
                if self._is_complete(pages_processed):
                    logger.info("Application complete after resume selection!")
                    return ApplicationResult(
                        status=ApplicationStatus.SUCCESS,
                        message="Application submitted successfully",
                        pages_processed=pages_processed,
                        url=job_url
                    )
                continue

            dom_state = self._dom_service.extract()
            logger.info(f"Found {dom_state.elementCount} elements")

            if self._detect_loop(current_url, dom_state.elementCount):
                logger.warning(f"LOOP DETECTED - same URL and element count {LOOP_DETECTION_THRESHOLD} times")
                return ApplicationResult(
                    status=ApplicationStatus.FAILED,
                    message="Stuck in form loop",
                    pages_processed=pages_processed,
                    url=job_url,
                )

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

            plan = self._claude.analyze_form(dom_state, self._profile, self._dom_service)

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

    def _detect_loop(self, url: str, element_count: int) -> bool:
        """Detect if stuck in loop (same URL + similar element count 3+ times)."""
        self._page_states.append((url, element_count))

        if len(self._page_states) >= LOOP_DETECTION_THRESHOLD:
            recent = self._page_states[-LOOP_DETECTION_THRESHOLD:]
            urls_same = all(s[0] == recent[0][0] for s in recent)
            counts_similar = all(
                abs(s[1] - recent[0][1]) <= LOOP_ELEMENT_COUNT_TOLERANCE
                for s in recent
            )
            if urls_same and counts_similar:
                return True
        return False

    def _is_account_creation_page(self, url: str, page_text: str) -> bool:
        """Detect pages requiring account creation."""
        url_lower = url.lower()
        for pattern in ACCOUNT_CREATION_URL_PATTERNS:
            if pattern in url_lower:
                return True

        text_lower = page_text.lower()
        matches = sum(1 for phrase in ACCOUNT_CREATION_CONTENT if phrase in text_lower)
        return matches >= 2

    def _handle_new_tab(self) -> None:
        """Handle popup URLs by navigating in current tab instead of switching."""
        popup_url = self._tabs.get_captured_popup_url()
        if popup_url and popup_url != "about:blank":
            logger.info(f"Popup captured during form, navigating to: {popup_url}")
            try:
                self._page.goto(popup_url)
            except Exception as e:
                error_msg = str(e).lower()
                if "err_aborted" not in error_msg and "aborted" not in error_msg:
                    raise
                logger.warning(f"Navigation aborted: {e}")
                self._page.wait(2000)
            self._dom_service = DomService(self._page)
            self._runner = ActionRunner(self._page, self._dom_service)
            self._page.wait(2000)
            self._tabs.close_extras(keep=1)

    def _click_next_button(self) -> bool:
        """Try to click Next/Continue/Submit button using semantic locators."""
        page = self._page.raw

        next_locator = (
            page.get_by_role("button", name=re.compile(r"next|continue|submit|review", re.IGNORECASE))
            .or_(page.get_by_role("link", name=re.compile(r"next|continue", re.IGNORECASE)))
            .or_(page.locator('[type="submit"]'))
            .or_(page.locator('[aria-label*="Next" i]'))
            .or_(page.locator('[aria-label*="Continue" i]'))
            .or_(page.locator('[aria-label*="Submit" i]'))
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

    def _is_complete(self, pages_processed: int = 0) -> bool:
        """Check if application was submitted using semantic locators."""
        if pages_processed < 2:
            return False

        page = self._page.raw
        current_url = self._page.url.lower()

        negative_signals = ["/job/", "/jobs/", "/careers/", "/viewjob", "/job-detail", "/apply", "linkedin.com/jobs/view"]
        if any(sig in current_url for sig in negative_signals):
            if not any(pos in current_url for pos in ["success", "submitted", "confirmed", "thank", "complete"]):
                return False

        completion_locator = (
            page.get_by_text(re.compile(r"application submitted|thank you for applying|successfully submitted|application received", re.IGNORECASE))
            .or_(page.locator('[data-test="application-complete"]'))
            .or_(page.locator('[data-testid*="success" i]'))
            .or_(page.locator('[data-testid*="complete" i]'))
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
