"""Execute actions using element refs."""
import logging

from playwright.sync_api import Locator

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

    def _fill_react_select(self, element: Locator, value: str) -> bool:
        """Handle React Select dropdowns (combobox role)."""
        try:
            element.click()
            self._page.wait(200)
            element.fill(value)
            self._page.wait(300)
            element.press("Enter")
            return True
        except Exception as e:
            logger.warning(f"React Select fill failed: {e}")
            return False

    def _execute_click(self, locator: Locator) -> None:
        """Click element, handling hidden radio/checkbox inputs."""
        if locator.is_visible():
            locator.click()
            return

        tag = locator.evaluate("el => el.tagName.toLowerCase()")
        input_type = locator.evaluate("el => el.type || ''")

        if tag == "input" and input_type in ("radio", "checkbox"):
            input_id = locator.evaluate("el => el.id")
            if input_id:
                label = self._page.raw.locator(f'label[for="{input_id}"]').first
                if label.count() > 0 and label.is_visible():
                    label.click()
                    return
            locator.evaluate("el => el.click()")
            return

        locator.click()

    def _execute_fill(self, element: Locator, value: str) -> bool:
        """Fill form element, detecting type."""
        tag = element.evaluate("el => el.tagName.toLowerCase()")
        role = element.get_attribute("role")

        if tag == "select":
            element.select_option(label=value)
        elif role == "combobox":
            return self._fill_react_select(element, value)
        else:
            element.clear()
            element.fill(value)
        return True

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
                self._execute_fill(loc, action.value)
            case SelectAction():
                selector = self._dom.get_selector(action.ref)
                loc = self._page.raw.locator(selector).first
                role = loc.get_attribute("role")
                if role == "combobox":
                    self._fill_react_select(loc, action.value)
                else:
                    loc.select_option(label=action.value)
            case ClickAction():
                selector = self._dom.get_selector(action.ref)
                loc = self._page.raw.locator(selector).first
                self._execute_click(loc)
            case UploadAction():
                selector = self._dom.get_selector(action.ref)
                loc = self._page.raw.locator(selector).first
                loc.set_input_files(action.file)
            case WaitAction():
                self._page.wait(action.ms)
