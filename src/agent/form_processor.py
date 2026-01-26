"""Form processing logic for multi-page application flows."""
import logging
import os
import re
import time
from typing import Optional

from ..browser.page import Page
from ..browser.tabs import TabManager
from ..extractor.dom_service import DomService, DomState, DomElement
from .claude import ClaudeAgent
from ..executor.runner import ActionRunner
from .page_classifier import PageClassifier
from .loop_detector import LoopDetector, MAX_SAME_STATE_COUNT
from .actions import ActionPlan, ClickAction
from .models import (
    JobSource, ApplicationStatus, ApplicationResult,
    ACCOUNT_CREATION_URL_PATTERNS, ACCOUNT_CREATION_CONTENT,
)
from .indeed_helpers import IndeedHelpers
from .success_detector import SuccessDetector
from .zero_actions_handler import ZeroActionsHandler, PageState

logger = logging.getLogger(__name__)


class FormProcessor:
    """Processes multi-page application forms."""

    def __init__(
        self, page: Page, dom_service: DomService, claude: ClaudeAgent,
        runner: ActionRunner, tabs: TabManager, profile: dict,
        resume_path: Optional[str], timeout_seconds: float, max_pages: int,
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
        self._loop_detector = LoopDetector()
        self._indeed_helpers = IndeedHelpers(page)
        self._success_detector = SuccessDetector(page.raw)
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        self._zero_handler = ZeroActionsHandler(page.raw, api_key)

    def process(self, job_url: str, source: Optional[JobSource] = None) -> ApplicationResult:
        """Process multi-page application form."""
        self._indeed_helpers.reset()
        self._success_detector.reset()

        pages_processed = 0
        stuck_count = 0
        last_url = ""
        start_time = time.time()

        while pages_processed < self._max_pages:
            elapsed = time.time() - start_time
            if elapsed > self._timeout_seconds:
                logger.warning(f"Application timed out after {elapsed:.1f}s")
                return ApplicationResult(ApplicationStatus.STUCK, f"Timed out after {elapsed:.1f}s", pages_processed, job_url)
            pages_processed += 1

            if source == JobSource.INDEED and self._indeed_helpers.dismiss_modal():
                pages_processed -= 1
                continue

            PageClassifier(self._page.raw).dismiss_overlays()
            current_url = self._page.url

            if PageClassifier(self._page.raw)._is_payment_page():
                logger.warning(f"PAYMENT PAGE DETECTED - aborting: {current_url}")
                return ApplicationResult(ApplicationStatus.FAILED, "Payment page detected - safety abort", pages_processed, job_url)

            try:
                page_text = self._page.raw.content()[:5000]
            except Exception:
                page_text = ""

            if self._is_account_creation_page(current_url, page_text):
                logger.warning(f"ACCOUNT CREATION PAGE DETECTED - aborting: {current_url}")
                return ApplicationResult(ApplicationStatus.FAILED, "Requires account creation", pages_processed, job_url)

            logger.info(f"=== Page {pages_processed} === URL: {current_url}")

            completion = self._success_detector.check()
            if completion.is_complete:
                return ApplicationResult(ApplicationStatus.SUCCESS, f"Application submitted ({completion.signal.value}: {completion.details})", pages_processed, job_url)

            if self._indeed_helpers.handle_resume_card():
                self._page.wait(1500)
                completion = self._success_detector.check()
                if completion.is_complete:
                    return ApplicationResult(ApplicationStatus.SUCCESS, f"Application submitted ({completion.signal.value}: {completion.details})", pages_processed, job_url)
                continue

            dom_state = self._dom_service.extract()
            logger.info(f"Found {dom_state.elementCount} elements")

            if dom_state.elementCount == 0:
                stuck_count += 1
                if stuck_count >= 3:
                    return ApplicationResult(ApplicationStatus.STUCK, "No interactive elements found", pages_processed, job_url)
                self._page.wait(2000)
                continue

            plan = self._claude.analyze_form(dom_state, self._profile, self._dom_service)
            if not plan:
                stuck_count += 1
                if stuck_count >= 3:
                    return ApplicationResult(ApplicationStatus.STUCK, "Failed to analyze form", pages_processed, job_url)
                continue

            plan = self._ensure_plan_has_submit(plan, dom_state)

            page_type_result = self._handle_page_type(plan, pages_processed, job_url)
            if page_type_result is not None:
                return page_type_result
            if self._is_job_listing_click(plan):
                self._execute_job_listing_click(plan)
                continue

            if len(plan.actions) == 0:
                input_count = sum(1 for e in dom_state.elements if e.get('tag') in ('input', 'select', 'textarea'))
                page_state, handled = self._zero_handler.classify_and_handle(input_count)

                if page_state == PageState.CONFIRMATION:
                    completion = self._success_detector.check()
                    if completion.is_complete:
                        return ApplicationResult(ApplicationStatus.SUCCESS, f"Application submitted ({completion.details})", pages_processed, job_url)
                elif page_state == PageState.ERROR_PAGE:
                    return ApplicationResult(ApplicationStatus.FAILED, "Error page detected", pages_processed, job_url)
                elif handled:
                    continue

            self._indeed_helpers.try_resume_upload(dom_state, self._resume_path, self._dom_service)
            logger.info(f"Executing plan: {plan.reasoning}")

            if any(a.action == "fill" for a in plan.actions):
                self._success_detector.mark_form_filled()

            PageClassifier(self._page.raw).dismiss_overlays()
            success = self._runner.execute(plan)

            self._page.wait(1000)
            completion = self._success_detector.check()
            if completion.is_complete:
                return ApplicationResult(ApplicationStatus.SUCCESS, f"Application submitted ({completion.signal.value}: {completion.details})", pages_processed, job_url)

            if source == JobSource.INDEED:
                self._indeed_helpers.dismiss_modal()
            if not success:
                logger.warning("Plan execution had errors")

            actions_executed = len(plan.actions)
            self._loop_detector.record_state(current_url, dom_state.elementCount, actions_executed, success)
            if self._loop_detector.is_looping():
                logger.warning(f"LOOP DETECTED - same state {MAX_SAME_STATE_COUNT} times")
                return ApplicationResult(ApplicationStatus.FAILED, "Stuck in form loop", pages_processed, job_url)

            self._page.wait(500)
            self._handle_new_tab()

            new_url = self._page.url
            if new_url == last_url == current_url:
                if not self._click_next_button():
                    stuck_count += 1
                    if stuck_count >= 3:
                        return ApplicationResult(ApplicationStatus.STUCK, "Could not advance to next page", pages_processed, job_url)
            else:
                stuck_count = 0
            last_url = current_url

        return ApplicationResult(ApplicationStatus.MAX_PAGES_REACHED, f"Reached max pages ({self._max_pages})", pages_processed, job_url)

    def _is_account_creation_page(self, url: str, page_text: str) -> bool:
        url_lower = url.lower()
        if any(p in url_lower for p in ACCOUNT_CREATION_URL_PATTERNS):
            return True
        text_lower = page_text.lower()
        return sum(1 for phrase in ACCOUNT_CREATION_CONTENT if phrase in text_lower) >= 2

    def _handle_new_tab(self) -> None:
        popup_url = self._tabs.get_captured_popup_url()
        if popup_url and popup_url != "about:blank":
            logger.info(f"Popup captured, navigating to: {popup_url}")
            try:
                self._page.goto(popup_url)
            except Exception as e:
                if "err_aborted" not in str(e).lower() and "aborted" not in str(e).lower():
                    raise
                self._page.wait(2000)
            self._dom_service = DomService(self._page)
            self._runner = ActionRunner(self._page, self._dom_service)
            self._page.wait(2000)
            self._tabs.close_extras(keep=1)

    def _click_next_button(self) -> bool:
        page = self._page.raw
        next_locator = (
            page.get_by_role("button", name=re.compile(r"next|continue|submit|review", re.IGNORECASE))
            .or_(page.get_by_role("link", name=re.compile(r"next|continue", re.IGNORECASE)))
            .or_(page.locator('[type="submit"]'))
            .or_(page.locator('[aria-label*="Next" i], [aria-label*="Continue" i], [aria-label*="Submit" i]'))
            .or_(page.locator('[data-testid*="next" i], [data-testid*="submit" i]'))
        )
        try:
            first_match = next_locator.first
            if first_match.is_visible(timeout=3000):
                first_match.click()
                self._page.wait(1500)
                logger.info("Clicked Next button successfully")
                return True
        except Exception as e:
            logger.debug(f"Next button locator failed: {e}")
        return False

    def _handle_page_type(
        self, plan: ActionPlan, pages_processed: int, job_url: str
    ) -> Optional[ApplicationResult]:
        """Handle confirmation page type, returning result if complete."""
        if plan.page_type == "confirmation":
            logger.info("Claude detected confirmation page")
            return ApplicationResult(
                ApplicationStatus.SUCCESS,
                "Confirmation page detected",
                pages_processed,
                job_url,
            )
        return None

    def _is_job_listing_click(self, plan: ActionPlan) -> bool:
        """Check if this is a job listing page with single Apply click."""
        return (
            plan.page_type == "job_listing"
            and len(plan.actions) == 1
            and plan.actions[0].action == "click"
        )

    def _execute_job_listing_click(self, plan: ActionPlan) -> None:
        """Execute single click action on job listing page."""
        logger.info("Job listing page - clicking Apply")
        self._runner.execute(plan)
        self._page.wait(1500)

    def _find_submit_button(self, dom_state: DomState) -> Optional[DomElement]:
        """Find best submit/next button from DOM elements."""
        keywords_priority = ["submit", "next", "continue", "review", "apply"]
        best_match: Optional[DomElement] = None
        best_priority = len(keywords_priority)

        for el in dom_state.elements:
            if not self._is_clickable_element(el):
                continue
            priority = self._get_button_priority(el, keywords_priority)
            if priority < best_priority:
                best_priority = priority
                best_match = el

        return best_match

    def _is_clickable_element(self, el: DomElement) -> bool:
        """Check if element is a clickable button/link."""
        if el.disabled:
            return False
        if el.tag in ("button", "a", "input"):
            return True
        if el.type in ("submit", "button"):
            return True
        return False

    def _get_button_priority(
        self, el: DomElement, keywords: list[str]
    ) -> int:
        """Get priority index for button based on keyword match."""
        text = (el.text or "").lower()
        label = (el.label or "").lower()
        btn_text = (el.buttonText or "").lower()
        combined = f"{text} {label} {btn_text}"

        for i, keyword in enumerate(keywords):
            if keyword in combined:
                return i
        return len(keywords)

    def _ensure_plan_has_submit(
        self, plan: ActionPlan, dom_state: DomState
    ) -> ActionPlan:
        """Ensure plan ends with submit button click."""
        if plan.page_type == "confirmation":
            return plan
        if not plan.actions:
            return plan
        if self._plan_ends_with_button_click(plan, dom_state):
            return plan

        button = self._find_submit_button(dom_state)
        if button:
            logger.info(f"Auto-appending click on {self._get_button_text(button)} button")
            plan.actions.append(ClickAction(ref=button.ref))
        return plan

    def _plan_ends_with_button_click(
        self, plan: ActionPlan, dom_state: DomState
    ) -> bool:
        """Check if plan's last action is a button click."""
        last_action = plan.actions[-1]
        if last_action.action != "click":
            return False

        for el in dom_state.elements:
            if el.ref == last_action.ref:
                return self._is_clickable_element(el)
        return False

    def _get_button_text(self, el: DomElement) -> str:
        """Get display text for a button element."""
        return el.buttonText or el.text or el.label or el.ref
