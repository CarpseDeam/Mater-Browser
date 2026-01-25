"""Multi-page job application workflow."""
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from ..browser.page import Page
from ..extractor.dom_service import DomService, DomState
from ..agent.claude import ClaudeAgent
from ..agent.actions import ActionPlan, UploadAction
from ..executor.runner import ActionRunner

logger = logging.getLogger(__name__)


class PageResult(Enum):
    """Result of processing a single page."""
    CONTINUE = "continue"
    SUBMITTED = "submitted"
    COMPLETE = "complete"
    FAILED = "failed"
    MAX_PAGES = "max_pages"


@dataclass
class ApplicationResult:
    """Result of full application attempt."""
    success: bool
    pages_processed: int
    result: PageResult
    reason: str


class ApplicationWorkflow:
    """Orchestrates multi-page job application flow."""

    def __init__(
        self,
        page: Page,
        profile: dict,
        resume_path: Optional[str] = None,
        max_pages: int = 15,
        page_timeout: int = 30000,
    ) -> None:
        self._page = page
        self._profile = profile
        self._resume_path = resume_path
        self._max_pages = max_pages
        self._page_timeout = page_timeout

        self._dom_service = DomService(page)
        self._agent = ClaudeAgent()
        self._runner = ActionRunner(page, self._dom_service)

    def run(self, url: str) -> ApplicationResult:
        """Run the full application workflow."""
        logger.info(f"Starting application: {url}")

        try:
            self._page.goto(url)
            self._page.wait(2000)
        except Exception as e:
            logger.error(f"Failed to load page: {e}")
            return ApplicationResult(False, 0, PageResult.FAILED, str(e))

        self._click_initial_apply()

        pages_processed = 0

        while pages_processed < self._max_pages:
            pages_processed += 1
            logger.info(f"=== Processing page {pages_processed} ===")

            try:
                dom_state = self._dom_service.extract(highlight=False)
                logger.info(f"Found {dom_state.elementCount} interactive elements")
            except Exception as e:
                logger.error(f"DOM extraction failed: {e}")
                return ApplicationResult(False, pages_processed, PageResult.FAILED, str(e))

            if self._is_completion_page(dom_state):
                logger.info("Application complete - reached confirmation page")
                return ApplicationResult(True, pages_processed, PageResult.COMPLETE, "Application submitted successfully")

            plan = self._agent.analyze_form(dom_state, self._profile, self._dom_service)

            if not plan:
                logger.error("Failed to get action plan")
                return ApplicationResult(False, pages_processed, PageResult.FAILED, "Claude failed to analyze form")

            logger.info(f"Plan: {plan.reasoning}")

            if self._resume_path:
                plan = self._inject_resume_upload(plan, dom_state)

            try:
                self._runner.execute(plan)
            except Exception as e:
                logger.error(f"Execution failed: {e}")
                return ApplicationResult(False, pages_processed, PageResult.FAILED, str(e))

            self._page.wait(2000)

            if self._detected_submission():
                logger.info("Application submitted!")
                return ApplicationResult(True, pages_processed, PageResult.SUBMITTED, "Application submitted")

            if not self._page_changed(dom_state):
                logger.warning("Page didn't change after actions - checking for errors")
                if self._has_validation_errors():
                    logger.error("Form has validation errors")
                    return ApplicationResult(False, pages_processed, PageResult.FAILED, "Form validation errors")
                self._page.wait(2000)

        logger.warning(f"Reached max pages ({self._max_pages})")
        return ApplicationResult(False, pages_processed, PageResult.MAX_PAGES, "Max pages reached")

    def _click_initial_apply(self) -> bool:
        """Click Easy Apply or Apply button if present."""
        apply_selectors = [
            'button.jobs-apply-button',
            'button[aria-label*="Apply"]',
            'button:has-text("Apply")',
            'button:has-text("Easy Apply")',
            'a:has-text("Apply")',
            '[data-automation="job-detail-apply"]',
        ]

        for selector in apply_selectors:
            try:
                btn = self._page.raw.locator(selector).first
                if btn.is_visible(timeout=2000):
                    logger.info(f"Clicking apply button: {selector}")
                    btn.click()
                    self._page.wait(2000)
                    return True
            except Exception:
                continue

        return False

    def _is_completion_page(self, dom_state: Optional[DomState]) -> bool:
        """Check if current page is a completion/thank you page."""
        completion_keywords = [
            "thank you",
            "application submitted",
            "successfully submitted",
            "application received",
            "we received your application",
            "application complete",
        ]

        try:
            page_text = self._page.raw.inner_text("body").lower()
        except Exception:
            return False

        for keyword in completion_keywords:
            if keyword in page_text:
                return True

        return False

    def _detected_submission(self) -> bool:
        """Check if we just submitted."""
        return self._is_completion_page(None)

    def _page_changed(self, old_state: DomState) -> bool:
        """Check if page content changed after actions."""
        try:
            new_state = self._dom_service.extract(highlight=False)
            diff = abs(new_state.elementCount - old_state.elementCount)
            url_changed = new_state.url != old_state.url
            return diff > 2 or url_changed
        except Exception:
            return True

    def _has_validation_errors(self) -> bool:
        """Check for form validation errors."""
        error_selectors = [
            '[class*="error"]',
            '[class*="invalid"]',
            '[aria-invalid="true"]',
            '.field-error',
            '.validation-error',
        ]

        for selector in error_selectors:
            try:
                if self._page.raw.locator(selector).count() > 0:
                    return True
            except Exception:
                continue

        return False

    def _inject_resume_upload(self, plan: ActionPlan, dom_state: DomState) -> ActionPlan:
        """Add resume upload action if file input exists and not already in plan."""
        for el in dom_state.elements:
            if el.tag == "input" and el.type == "file":
                refs_in_plan = [getattr(a, 'ref', None) for a in plan.actions]
                if el.ref not in refs_in_plan:
                    logger.info(f"Injecting resume upload for {el.ref}")
                    upload = UploadAction(ref=el.ref, file=self._resume_path)
                    plan.actions.insert(0, upload)
                break

        return plan
