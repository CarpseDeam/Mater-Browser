"""Claude agent using DOM service."""
import json
import logging
from typing import Optional

from anthropic import Anthropic

from .actions import ActionPlan
from .prompts import SYSTEM_PROMPT, build_form_prompt
from ..extractor.dom_service import DomState, DomService

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
            return ActionPlan(**plan_data)

        except Exception as e:
            logger.error(f"Claude analysis failed: {e}")
            return None
