"""Claude agent using DOM service."""
import json
import logging
from typing import Optional

from anthropic import Anthropic

from .actions import Action, ActionPlan
from .prompts import SYSTEM_PROMPT, build_form_prompt
from ..extractor.dom_service import DomElement, DomState, DomService

logger = logging.getLogger(__name__)


class ClaudeAgent:
    """Claude-powered form analysis using indexed DOM elements."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client = Anthropic()

    def analyze_form(
        self,
        dom_state: DomState,
        profile: dict,
        dom_service: DomService,
    ) -> Optional[ActionPlan]:
        """Analyze DOM and return action plan with refs."""
        logger.info(f"Analyzing {dom_state.elementCount} elements")

        dom_text = dom_service.format_for_llm(dom_state)

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": build_form_prompt(dom_text, profile),
                    }
                ],
            )

            content = response.content[0].text
            logger.debug(f"Claude response: {content}")

            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            plan_data = json.loads(content)
            plan = ActionPlan(**plan_data)
            plan = self._validate_plan(plan, dom_state)
            return plan

        except Exception as e:
            logger.error(f"Claude analysis failed: {e}")
            return None

    def _validate_plan(
        self,
        plan: ActionPlan,
        dom_state: DomState,
    ) -> ActionPlan:
        """Remove actions with invalid refs or incompatible action types."""
        ref_to_element = {el.ref: el for el in dom_state.elements}
        valid_refs = set(ref_to_element.keys())
        valid_actions: list[Action] = []

        for action in plan.actions:
            ref = getattr(action, "ref", None)
            if ref is None:
                valid_actions.append(action)
                continue

            if ref not in valid_refs:
                logger.warning(f"Removing action with invalid ref: {ref}")
                continue

            element = ref_to_element[ref]
            if not self._validate_action_type(action, element):
                logger.warning(f"Removing invalid {action.action} for {element.tag}")
                continue

            valid_actions.append(action)

        plan.actions = valid_actions
        return plan

    def _validate_action_type(self, action: Action, element: DomElement) -> bool:
        """Check if action is valid for element type."""
        action_type = action.action

        if action_type == "fill":
            valid_tags = ("input", "textarea")
            return element.tag in valid_tags or element.type == "textbox"

        if action_type == "select":
            return element.tag == "select" or element.type == "combobox"

        if action_type == "click":
            return True

        if action_type == "upload":
            return element.tag == "input" and element.type == "file"

        return True
