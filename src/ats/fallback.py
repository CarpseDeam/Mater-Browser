"""Claude fallback for unknown ATS systems."""
import logging
from typing import Optional, Any

from playwright.sync_api import Page

from .base_handler import FormPage, PageResult

logger = logging.getLogger(__name__)


class ClaudeFallback:
    """Fallback to Claude for unknown ATS systems."""

    def __init__(
        self,
        page: Page,
        claude_agent: Any,
        profile: dict,
        resume_path: Optional[str] = None,
    ) -> None:
        self._page = page
        self._claude = claude_agent
        self._profile = profile
        self._resume_path = resume_path

    def fill_current_page(self, dom_service: Any) -> PageResult:
        """Use Claude to fill the current page."""
        logger.info("Using Claude fallback for unknown ATS")

        dom_state = dom_service.extract()
        plan = self._claude.analyze_form(dom_state, self._profile, dom_service)

        if not plan:
            return PageResult(
                False, FormPage.UNKNOWN, "Claude could not analyze page", False
            )

        if plan.page_type == "confirmation":
            return PageResult(
                True, FormPage.CONFIRMATION, "Confirmation detected", False
            )

        action_count = len(plan.actions) if plan.actions else 0
        return PageResult(
            True, FormPage.UNKNOWN, f"Claude returned {action_count} actions", True
        )
