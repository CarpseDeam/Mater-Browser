"""DOM extraction service using buildDomTree.js approach."""
import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from ..browser.page import Page

logger = logging.getLogger(__name__)

_JS_PATH = Path(__file__).parent / "dom_tree.js"
_DOM_TREE_JS: Optional[str] = None


def _get_js() -> str:
    global _DOM_TREE_JS
    if _DOM_TREE_JS is None:
        _DOM_TREE_JS = _JS_PATH.read_text(encoding="utf-8")
    return _DOM_TREE_JS


class DomElement(BaseModel):
    """A single interactive element from the DOM."""

    ref: str
    index: int
    tag: str
    type: Optional[str] = None
    name: Optional[str] = None
    id: Optional[str] = None
    selector: str
    label: Optional[str] = None
    placeholder: Optional[str] = None
    value: Optional[str] = None
    text: Optional[str] = None
    required: bool = False
    disabled: bool = False
    options: Optional[list[dict]] = None
    buttonText: Optional[str] = None
    href: Optional[str] = None


class DomState(BaseModel):
    """Complete DOM extraction result."""

    url: str
    title: str
    elementCount: int
    elements: list[DomElement]
    selectorMap: dict[str, str]


class DomService:
    """Extracts interactive elements from a page using buildDomTree.js."""

    def __init__(self, page: Page) -> None:
        self._page = page
        self._selector_map: dict[str, str] = {}

    def extract(self, highlight: bool = False) -> DomState:
        """Extract all interactive elements from the page."""
        logger.info("Extracting DOM elements...")

        js_code = _get_js()
        options = json.dumps({"doHighlightElements": highlight, "viewportExpansion": 0})

        result = self._page.raw.evaluate(f"({js_code})({options})")

        state = DomState(**result)
        self._selector_map = state.selectorMap

        logger.info(f"Extracted {state.elementCount} interactive elements")
        return state

    def get_selector(self, ref: str) -> Optional[str]:
        """Get CSS selector for an element ref."""
        return self._selector_map.get(ref)

    def format_for_llm(self, state: DomState) -> str:
        """Format DOM state as clean text for LLM consumption."""
        lines = [f"Page: {state.title}", f"URL: {state.url}", "", "Interactive Elements:"]

        for el in state.elements:
            if el.disabled:
                continue

            parts = [el.ref]

            if el.type:
                parts.append(f"[{el.tag}:{el.type}]")
            else:
                parts.append(f"[{el.tag}]")

            if el.label:
                parts.append(f'"{el.label}"')
            elif el.buttonText:
                parts.append(f'"{el.buttonText}"')
            elif el.text and len(el.text) < 50:
                parts.append(f'"{el.text}"')

            if el.placeholder:
                parts.append(f'placeholder="{el.placeholder}"')
            if el.required:
                parts.append("required")
            if el.options:
                opt_texts = [o["text"] for o in el.options[:5]]
                if len(el.options) > 5:
                    opt_texts.append("...")
                parts.append(f"options={opt_texts}")
            if el.value and el.tag not in ("button", "a"):
                parts.append(f'value="{el.value[:30]}"')
            if el.href:
                parts.append(f'href="{el.href[:50]}"')

            lines.append(" ".join(parts))

        return "\n".join(lines)

    def find_apply_buttons(self, state: DomState) -> list[DomElement]:
        """Find elements that look like Apply buttons.

        Args:
            state: DomState from extract().

        Returns:
            List of DomElement instances that match Apply button patterns.
        """
        apply_keywords = ["apply", "easy apply", "apply now", "submit application"]
        matches = []

        for el in state.elements:
            if el.disabled:
                continue

            text = (el.text or "").lower()
            label = (el.label or "").lower()
            btn_text = (el.buttonText or "").lower()

            combined = f"{text} {label} {btn_text}"

            if any(kw in combined for kw in apply_keywords):
                if el.tag in ("button", "a", "input") or el.type in ("submit", "button"):
                    matches.append(el)

        return matches

    def find_next_buttons(self, state: DomState) -> list[DomElement]:
        """Find elements that look like Next/Continue/Submit buttons.

        Args:
            state: DomState from extract().

        Returns:
            List of DomElement instances that match navigation button patterns.
        """
        next_keywords = ["next", "continue", "submit", "review", "proceed", "save & continue"]
        matches = []

        for el in state.elements:
            if el.disabled:
                continue

            text = (el.text or "").lower()
            label = (el.label or "").lower()
            btn_text = (el.buttonText or "").lower()

            combined = f"{text} {label} {btn_text}"

            if any(kw in combined for kw in next_keywords):
                if el.tag in ("button", "input") or el.type in ("submit", "button"):
                    matches.append(el)

        return matches

    def find_file_inputs(self, state: DomState) -> list[DomElement]:
        """Find file upload inputs.

        Args:
            state: DomState from extract().

        Returns:
            List of DomElement instances for file inputs.
        """
        return [
            el for el in state.elements
            if el.tag == "input" and el.type == "file" and not el.disabled
        ]

    def find_resume_upload(self, state: DomState) -> Optional[DomElement]:
        """Find the resume/CV upload input.

        Args:
            state: DomState from extract().

        Returns:
            DomElement for resume upload if found, None otherwise.
        """
        resume_keywords = ["resume", "cv", "curriculum"]
        file_inputs = self.find_file_inputs(state)

        for el in file_inputs:
            label = (el.label or "").lower()
            name = (el.name or "").lower()
            element_id = (el.id or "").lower()

            combined = f"{label} {name} {element_id}"

            if any(kw in combined for kw in resume_keywords):
                return el

        if file_inputs:
            return file_inputs[0]

        return None
