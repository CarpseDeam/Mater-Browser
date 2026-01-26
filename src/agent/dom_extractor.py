"""DOM extraction for apply button candidate detection."""
import logging
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import Page as PlaywrightPage

logger = logging.getLogger(__name__)


@dataclass
class ElementCandidate:
    """Candidate element for apply button detection."""
    selector: str
    tag: str
    text: str
    role: Optional[str]
    aria_label: Optional[str]
    href: Optional[str]
    data_testid: Optional[str]
    is_visible: bool
    score: float = field(default=0.0)


_EXTRACTION_SCRIPT: str = '''() => {
    const candidates = document.querySelectorAll('button, a, [role="button"], [role="link"]');
    return Array.from(candidates).map((el, idx) => {
        const text = (el.textContent || '').trim().slice(0, 100);
        const ariaLabel = el.getAttribute('aria-label') || '';
        const testId = el.getAttribute('data-testid') || '';
        const searchText = (text + ' ' + ariaLabel + ' ' + testId).toLowerCase();

        if (!searchText.includes('apply')) {
            return null;
        }

        const rect = el.getBoundingClientRect();
        return {
            idx: idx,
            tag: el.tagName.toLowerCase(),
            text: text,
            role: el.getAttribute('role'),
            aria_label: ariaLabel || null,
            href: el.getAttribute('href'),
            data_testid: testId || null,
            is_visible: el.offsetParent !== null && rect.width > 0 && rect.height > 0,
        };
    }).filter(e => e !== null);
}'''


class DomExtractor:
    """Extracts apply button candidates from DOM."""

    def __init__(self, page: PlaywrightPage) -> None:
        self._page = page

    def extract_candidates(self) -> list[ElementCandidate]:
        """Batch extract all potential apply button candidates."""
        raw_elements = self._page.evaluate(_EXTRACTION_SCRIPT)

        candidates = []
        for raw in raw_elements:
            selector = self._build_selector(raw)
            candidate = ElementCandidate(
                selector=selector,
                tag=raw['tag'],
                text=raw['text'],
                role=raw.get('role'),
                aria_label=raw.get('aria_label'),
                href=raw.get('href'),
                data_testid=raw.get('data_testid'),
                is_visible=raw['is_visible'],
            )
            candidates.append(candidate)

        return candidates

    def _build_selector(self, raw: dict) -> str:
        """Build a reliable CSS selector for a candidate element."""
        if raw.get('data_testid'):
            return f'[data-testid="{raw["data_testid"]}"]'

        if raw.get('aria_label'):
            escaped = raw['aria_label'].replace('"', '\\"')
            return f'{raw["tag"]}[aria-label="{escaped}"]'

        text = raw.get('text', '').strip()
        if text and len(text) < 50:
            escaped_text = text.replace('"', '\\"')
            return f'{raw["tag"]}:text-is("{escaped_text}")'

        base_query = 'button, a, [role="button"], [role="link"]'
        return f':is({base_query}) >> nth={raw["idx"]}'
