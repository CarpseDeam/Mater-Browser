"""LinkedIn Easy Apply flow handler."""
import logging
from typing import Optional

from ..browser.page import Page
from ..browser.tabs import TabManager
from .page_classifier import PageClassifier, PageType
from .models import (
    ApplicationStatus,
    ApplicationResult,
    MEDIUM_WAIT_MS,
    LONG_WAIT_MS,
    PAGE_LOAD_TIMEOUT_MS,
    MAX_POPUP_WAIT_ATTEMPTS,
)
from .answer_engine import AnswerEngine
from .linkedin_form_filler import LinkedInFormFiller

logger = logging.getLogger(__name__)


class LinkedInFlow:
    """Handles LinkedIn Easy Apply flow."""

    def __init__(
        self,
        page: Page,
        tabs: TabManager,
        max_pages: int,
    ) -> None:
        self._page = page
        self._tabs = tabs
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
            self._page.raw.wait_for_load_state("domcontentloaded", timeout=5000)
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

        if page_type != PageType.EASY_APPLY:
            logger.info("Not Easy Apply - skipping (Easy Apply only)")
            return ApplicationResult(
                status=ApplicationStatus.SKIPPED,
                message="Not Easy Apply - Easy Apply only",
                url=job_url,
            )

        return self._process_easy_apply(job_url)

    def _process_easy_apply(self, job_url: str) -> ApplicationResult:
        """Process LinkedIn Easy Apply using deterministic form filler."""
        logger.info("Using deterministic form filler for Easy Apply")

        answer_engine = AnswerEngine()
        filler = LinkedInFormFiller(self._page.raw, answer_engine)

        last_page_hash = ""
        stuck_count = 0
        max_stuck = 3  # Increase tolerance

        for page_num in range(self._max_pages):
            logger.info(f"Processing page {page_num + 1}/{self._max_pages}")
            self._page.wait(1000)

            if filler.is_confirmation_page():
                logger.info("Confirmation page detected - application submitted!")
                filler.close_modal()
                return ApplicationResult(
                    status=ApplicationStatus.SUCCESS,
                    message="Application submitted",
                    pages_processed=page_num + 1,
                    url=job_url,
                )

            # Get current page hash to detect stuck
            current_hash = self._get_modal_hash()
            logger.debug(f"Page hash: '{current_hash}' (last: '{last_page_hash}')")

            # Only count as stuck if we have a valid hash (not empty)
            if current_hash and current_hash != "empty" and current_hash == last_page_hash:
                stuck_count += 1
                logger.warning(f"Same page hash detected ({stuck_count}/{max_stuck})")
                if stuck_count >= max_stuck:
                    logger.warning(f"Stuck on same page {stuck_count} times, aborting")
                    break
            else:
                stuck_count = 0
                last_page_hash = current_hash

            # Fill the form
            modal_found = filler.fill_current_modal()
            logger.info(f"Page {page_num + 1}: Modal found={modal_found}")

            # Click next button
            if not filler.click_next():
                logger.warning(f"Page {page_num + 1}: Could not find next button")
                # Retry once after waiting
                self._page.wait(1000)
                if not filler.click_next():
                    logger.warning("Next button still not found after retry, aborting")
                    break

            self._page.wait(1000)

        return ApplicationResult(
            status=ApplicationStatus.FAILED,
            message="Max pages reached or stuck",
            pages_processed=page_num + 1,
            url=job_url,
        )

    def _get_modal_hash(self) -> str:
        """Get a hash of the current modal state to detect if we're stuck."""
        hash_parts = []

        # Try progress bar percentage
        try:
            progress = self._page.raw.locator("progress").first
            if progress.is_visible(timeout=500):
                value = progress.get_attribute("value") or ""
                max_val = progress.get_attribute("max") or "100"
                if value:
                    hash_parts.append(f"progress:{value}/{max_val}")
        except Exception:
            pass

        # Try aria-valuenow on progress (LinkedIn uses this)
        try:
            progress_aria = self._page.raw.locator("[role='progressbar']").first
            if progress_aria.is_visible(timeout=500):
                value = progress_aria.get_attribute("aria-valuenow") or ""
                if value:
                    hash_parts.append(f"aria-progress:{value}")
        except Exception:
            pass

        # Count form elements in modal
        modal_selectors = [
            ".jobs-easy-apply-modal",
            "[data-test-modal]",
            ".artdeco-modal",
            "[role='dialog']",
        ]
        for modal_sel in modal_selectors:
            try:
                modal = self._page.raw.locator(modal_sel).first
                if modal.is_visible(timeout=300):
                    inputs = modal.locator("input:visible").count()
                    selects = modal.locator("select:visible").count()
                    textareas = modal.locator("textarea:visible").count()
                    fieldsets = modal.locator("fieldset:visible").count()
                    hash_parts.append(f"form:{inputs}i/{selects}s/{textareas}t/{fieldsets}f")
                    break
            except Exception:
                continue

        # Get visible question text as part of hash
        try:
            labels = self._page.raw.locator(".jobs-easy-apply-modal .fb-form-element-label").all()
            label_texts = []
            for label in labels[:3]:  # First 3 labels
                try:
                    text = label.text_content()
                    if text:
                        label_texts.append(text[:20])  # First 20 chars
                except Exception:
                    pass
            if label_texts:
                hash_parts.append(f"labels:{','.join(label_texts)}")
        except Exception:
            pass

        result = "|".join(hash_parts) if hash_parts else "empty"
        logger.debug(f"Modal hash components: {result}")
        return result
