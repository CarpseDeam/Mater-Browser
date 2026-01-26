"""Handle scenarios where Claude returns 0 actions."""
import logging
import re
from enum import Enum
from typing import Optional, Tuple

from playwright.sync_api import Page

from .vision_fallback import VisionFallback

logger = logging.getLogger(__name__)


class PageState(Enum):
    """Classification of page state when 0 actions returned."""
    JOB_DESCRIPTION = "job_description"
    CONFIRMATION = "confirmation"
    LOADING = "loading"
    ERROR_PAGE = "error_page"
    UNKNOWN = "unknown"


class ZeroActionsHandler:
    """Handles situations where Claude returns 0 actions."""

    def __init__(self, page: Page, api_key: Optional[str] = None) -> None:
        self._page = page
        self._vision = VisionFallback(page, api_key)

    def classify_and_handle(self, input_count: int) -> Tuple[PageState, bool]:
        """
        Classify page state and attempt recovery.

        Returns:
            Tuple of (PageState, handled: bool)
            If handled=True, caller should continue loop (page state changed)
            If handled=False, caller should check other exit conditions
        """
        state = self._classify_page(input_count)
        logger.info(f"Zero actions - page classified as: {state.value}")

        if state == PageState.JOB_DESCRIPTION:
            return state, self._handle_job_description()
        elif state == PageState.CONFIRMATION:
            return state, False
        elif state == PageState.LOADING:
            return state, self._handle_loading()
        elif state == PageState.ERROR_PAGE:
            return state, False
        else:
            return state, self._try_scroll_and_find_button()

    def _classify_page(self, input_count: int) -> PageState:
        """Determine what kind of page we're on."""
        url = self._page.url.lower()

        success_patterns = ["confirmation", "thank", "success", "submitted", "post-apply", "applied"]
        if any(p in url for p in success_patterns):
            return PageState.CONFIRMATION

        error_patterns = ["error", "404", "not-found", "expired"]
        if any(p in url for p in error_patterns):
            return PageState.ERROR_PAGE

        try:
            content = self._page.content().lower()

            if self._page.locator("[class*='loading'], [class*='spinner'], .loader").count() > 0:
                return PageState.LOADING

            if input_count < 3:
                apply_btn = self._page.locator("button, a").filter(has_text=re.compile(r"apply", re.IGNORECASE))
                if apply_btn.count() > 0:
                    return PageState.JOB_DESCRIPTION

                success_text = ["thank you", "application submitted", "successfully", "received your application"]
                if any(t in content for t in success_text):
                    return PageState.CONFIRMATION
        except Exception as e:
            logger.debug(f"Page classification error: {e}")

        return PageState.UNKNOWN

    def _handle_job_description(self) -> bool:
        """Try to find and click Apply button on job description page."""
        logger.info("Attempting to find Apply button on job description page")

        try:
            self._page.evaluate("window.scrollBy(0, 500)")
            self._page.wait_for_timeout(500)
        except Exception:
            pass

        apply_patterns = [
            self._page.get_by_role("button", name=re.compile(r"^apply", re.IGNORECASE)),
            self._page.get_by_role("link", name=re.compile(r"^apply", re.IGNORECASE)),
            self._page.locator("button, a").filter(has_text=re.compile(r"apply now", re.IGNORECASE)),
            self._page.locator("button, a").filter(has_text=re.compile(r"apply for", re.IGNORECASE)),
            self._page.locator("[class*='apply'], [id*='apply']").filter(has_text=re.compile(r"apply", re.IGNORECASE)),
        ]

        for locator in apply_patterns:
            try:
                if locator.first.is_visible(timeout=1000):
                    logger.info("Found Apply button - clicking")
                    locator.first.click()
                    self._page.wait_for_timeout(2000)
                    return True
            except Exception:
                continue

        logger.info("DOM detection failed - trying vision fallback")
        if self._vision.find_and_click_apply():
            return True

        return self._try_scroll_and_find_button()

    def _handle_loading(self) -> bool:
        """Wait for loading to complete."""
        logger.info("Page appears to be loading - waiting")
        try:
            self._page.wait_for_load_state("networkidle", timeout=5000)
            return True
        except Exception:
            self._page.wait_for_timeout(2000)
            return True

    def _try_scroll_and_find_button(self) -> bool:
        """Scroll down and look for any actionable button."""
        logger.info("Scrolling to find actionable elements")

        for _ in range(3):
            try:
                self._page.evaluate("window.scrollBy(0, 600)")
                self._page.wait_for_timeout(800)

                action_btn = self._page.locator("button, a").filter(
                    has_text=re.compile(r"apply|submit|continue|next", re.IGNORECASE)
                ).first

                if action_btn.is_visible(timeout=500):
                    logger.info("Found action button after scroll - clicking")
                    action_btn.click()
                    self._page.wait_for_timeout(1500)
                    return True
            except Exception:
                continue

        logger.info("All scroll attempts failed - final vision fallback")
        if self._vision.find_and_click_apply():
            return True

        return False
