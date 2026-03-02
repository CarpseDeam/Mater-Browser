"""LinkedIn Easy Apply flow handler."""
import logging
import time
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

EASY_APPLY_TIMEOUT_SECONDS: float = 120.0


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

    def _ensure_clean_state(self) -> None:
        """Dismiss any open modals/dialogs before starting new application."""
        try:
            dialog = self._page.raw.locator("[role='dialog']").first
            if dialog.is_visible(timeout=500):
                logger.info("Dismissing open dialog")
                dismiss_selectors = [
                    "button[aria-label*='Dismiss' i]",
                    "[data-test-modal-close-btn]",
                    "button.artdeco-modal__dismiss",
                ]
                for selector in dismiss_selectors:
                    try:
                        btn = self._page.raw.locator(selector).first
                        if btn.is_visible(timeout=500):
                            btn.click()
                            self._page.wait(500)
                            return
                    except Exception:
                        continue

                self._page.raw.keyboard.press("Escape")
                self._page.wait(500)

        except Exception:
            pass

        try:
            modal = self._page.raw.locator(".artdeco-modal").first
            if modal.is_visible(timeout=500):
                logger.info("Dismissing open modal")
                self._page.raw.keyboard.press("Escape")
                self._page.wait(500)
        except Exception:
            pass

    def apply(self, job_url: str) -> ApplicationResult:
        """
        Handle LinkedIn Easy Apply flow.

        Easy Apply opens a modal on the same page - no navigation required.
        LinkedIn uses SPA routing which can cause ERR_ABORTED on goto().
        """
        logger.info("Using LinkedIn Easy Apply flow")

        self._ensure_clean_state()

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

        if page_type != PageType.EASY_APPLY:
            logger.info("Not Easy Apply - skipping (Easy Apply only)")
            return ApplicationResult(
                status=ApplicationStatus.SKIPPED,
                message="Not Easy Apply - Easy Apply only",
                url=job_url,
            )

        if not classifier.click_apply_button():
            return ApplicationResult(
                status=ApplicationStatus.NO_APPLY_BUTTON,
                message="Could not find Easy Apply button",
                url=job_url,
            )

        self._page.wait(LONG_WAIT_MS)

        # Verify modal appeared
        modal_appeared = False
        for sel in [".jobs-easy-apply-modal", ".artdeco-modal", '[role="dialog"]']:
            try:
                if self._page.raw.locator(sel).first.is_visible(timeout=2000):
                    modal_appeared = True
                    break
            except Exception:
                continue

        if not modal_appeared:
            logger.warning("Easy Apply modal did not appear after clicking button")
            return ApplicationResult(
                status=ApplicationStatus.FAILED,
                message="Easy Apply modal did not open",
                url=job_url,
            )

        return self._process_easy_apply(job_url)

    def _close_modal(self) -> None:
        """Close Easy Apply modal and handle discard confirmation."""
        # Try dismiss button first
        dismiss_selectors = [
            'button[aria-label="Dismiss"]',
            '[data-test-modal-close-btn]',
            'button.artdeco-modal__dismiss',
        ]
        for selector in dismiss_selectors:
            try:
                btn = self._page.raw.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    self._page.wait(500)
                    break
            except Exception:
                continue

        # Handle "Discard application?" confirmation
        try:
            discard_btn = self._page.raw.locator('button[data-test-dialog-primary-btn]').first
            if discard_btn.is_visible(timeout=1000):
                discard_btn.click()
                self._page.wait(500)
                return
        except Exception:
            pass

        # Try clicking "Discard" by text
        try:
            discard_text = self._page.raw.locator('button:has-text("Discard")').first
            if discard_text.is_visible(timeout=1000):
                discard_text.click()
                self._page.wait(500)
                return
        except Exception:
            pass

        # Nuclear: Escape
        try:
            self._page.raw.keyboard.press("Escape")
            self._page.wait(500)
        except Exception:
            pass

    def _process_easy_apply(self, job_url: str) -> ApplicationResult:
        """Process LinkedIn Easy Apply using deterministic form filler."""
        logger.info("Using deterministic form filler for Easy Apply")

        answer_engine = AnswerEngine()
        filler = LinkedInFormFiller(self._page.raw, answer_engine)

        start_time = time.time()
        last_page_hash = ""
        stuck_count = 0
        max_stuck = 3
        page_errors = 0

        for page_num in range(self._max_pages):
            elapsed = time.time() - start_time
            if elapsed > EASY_APPLY_TIMEOUT_SECONDS:
                logger.warning(f"Easy Apply timeout after {elapsed:.1f}s")
                self._close_modal()
                return ApplicationResult(
                    status=ApplicationStatus.FAILED,
                    message="Easy Apply timeout",
                    pages_processed=page_num + 1,
                    url=job_url,
                )

            try:
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

                current_hash = self._get_modal_hash()
                logger.debug(f"Page hash: '{current_hash}' (last: '{last_page_hash}')")

                if current_hash and current_hash != "empty" and current_hash == last_page_hash:
                    stuck_count += 1
                    logger.warning(f"Same page hash detected ({stuck_count}/{max_stuck})")
                    if stuck_count >= max_stuck:
                        logger.warning("Attempting stuck recovery before aborting")
                        recovery_success = False

                        try:
                            if filler.check_and_fix_errors():
                                logger.info("Fixed errors during stuck recovery")

                            try:
                                modal = self._page.raw.locator(".jobs-easy-apply-modal").first
                                if modal.is_visible(timeout=500):
                                    modal.evaluate("el => el.scrollTop += 300")
                                    logger.info("Scrolled modal content down")
                            except Exception:
                                pass

                            self._page.wait(500)
                            filler.fill_current_modal()
                            self._page.wait(500)

                            if filler.click_next():
                                logger.info("Stuck recovery successful - continuing")
                                stuck_count = 0
                                recovery_success = True
                            else:
                                logger.warning("Stuck recovery failed - next button not found")

                        except Exception as e:
                            logger.warning(f"Stuck recovery exception: {e}")

                        if not recovery_success:
                            logger.warning(f"Stuck on same page {max_stuck} times, aborting")
                            self._close_modal()
                            break
                else:
                    stuck_count = 0
                    last_page_hash = current_hash

                modal_found = filler.fill_current_modal()
                logger.info(f"Page {page_num + 1}: Modal found={modal_found}")

                if not modal_found:
                    if filler.is_confirmation_page():
                        logger.info("Confirmation page detected after fill")
                        filler.close_modal()
                        return ApplicationResult(
                            status=ApplicationStatus.SUCCESS,
                            message="Application submitted",
                            pages_processed=page_num + 1,
                            url=job_url,
                        )
                    logger.warning("No modal found, aborting")
                    self._close_modal()
                    break

                if not filler.click_next():
                    logger.warning(f"Page {page_num + 1}: Could not find next button")
                    self._page.wait(1000)
                    if not filler.click_next():
                        logger.warning("Next button still not found after retry, aborting")
                        self._close_modal()
                        break

                self._page.wait(500)
                if filler.check_and_fix_errors():
                    logger.info("Fixed validation errors, retrying next")
                    filler.click_next()
                    self._page.wait(500)
                if filler.is_confirmation_page():
                    logger.info("Confirmation page detected after click")
                    filler.close_modal()
                    return ApplicationResult(
                        status=ApplicationStatus.SUCCESS,
                        message="Application submitted",
                        pages_processed=page_num + 1,
                        url=job_url,
                    )

                page_errors = 0

            except Exception as e:
                logger.warning(f"Error on page {page_num + 1}: {e}")
                page_errors += 1
                if page_errors >= 2:
                    logger.warning("Two consecutive page errors, aborting")
                    self._close_modal()
                    break
                continue

        self._close_modal()
        return ApplicationResult(
            status=ApplicationStatus.FAILED,
            message="Max pages reached or stuck",
            pages_processed=page_num + 1,
            url=job_url,
        )

    def _get_modal_hash(self) -> str:
        """Get a hash of the current modal state to detect if we're stuck (2026 structure)."""
        hash_parts = []

        # Try progress bar percentage (standard HTML5)
        try:
            progress = self._page.raw.locator("progress").first
            if progress.is_visible(timeout=500):
                value = progress.get_attribute("value") or ""
                max_val = progress.get_attribute("max") or "100"
                if value:
                    hash_parts.append(f"progress:{value}/{max_val}")
        except Exception:
            pass

        # Try aria-valuenow on progressbar role (LinkedIn 2026 uses this)
        try:
            progress_aria = self._page.raw.locator("[role='progressbar']").first
            if progress_aria.is_visible(timeout=500):
                value = progress_aria.get_attribute("aria-valuenow") or ""
                max_val = progress_aria.get_attribute("aria-valuemax") or "100"
                if value:
                    hash_parts.append(f"aria-progress:{value}/{max_val}")
        except Exception:
            pass

        # Count form elements in modal (priority order for 2026)
        modal_selectors = [
            ".jobs-easy-apply-modal",  # Primary modal class
            "[role='dialog']",  # ARIA dialog role (most reliable)
            ".artdeco-modal",  # Artdeco modal system
            "[data-test-modal]",  # Test attribute fallback
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
