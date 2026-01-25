"""Execute actions using element refs."""
import logging

from ..agent.actions import (
    Action,
    ActionPlan,
    ClickAction,
    FillAction,
    SelectAction,
    UploadAction,
    WaitAction,
)
from ..browser.page import Page
from ..extractor.dom_service import DomService

logger = logging.getLogger(__name__)


class ActionRunner:
    """Executes action plans using element refs."""

    def __init__(self, page: Page, dom_service: DomService) -> None:
        self._page = page
        self._dom = dom_service

    def execute(self, plan: ActionPlan) -> bool:
        """Execute all actions, resolving refs to selectors."""
        logger.info(f"Executing {len(plan.actions)} actions")
        logger.info(f"Reasoning: {plan.reasoning}")

        for i, action in enumerate(plan.actions):
            ref = getattr(action, "ref", None)
            if ref:
                selector = self._dom.get_selector(ref)
                if not selector:
                    logger.error(f"Unknown ref: {ref}")
                    continue
                logger.info(f"Action {i + 1}: {action.action} {ref} -> {selector}")
            else:
                logger.info(f"Action {i + 1}: {action.action}")

            try:
                self._execute_action(action)
                self._page.wait(500)
            except Exception as e:
                logger.error(f"Action failed: {e}")
                return False

        return True

    def _execute_action(self, action: Action) -> None:
        match action:
            case FillAction():
                selector = self._dom.get_selector(action.ref)
                loc = self._page.raw.locator(selector).first
                loc.clear()
                loc.fill(action.value)
            case SelectAction():
                selector = self._dom.get_selector(action.ref)
                loc = self._page.raw.locator(selector).first
                loc.select_option(label=action.value)
            case ClickAction():
                selector = self._dom.get_selector(action.ref)
                loc = self._page.raw.locator(selector).first
                loc.click()
            case UploadAction():
                selector = self._dom.get_selector(action.ref)
                loc = self._page.raw.locator(selector).first
                loc.set_input_files(action.file)
            case WaitAction():
                self._page.wait(action.ms)
