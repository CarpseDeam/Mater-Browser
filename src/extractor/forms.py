"""Form element extraction from page."""
import logging

from ..browser.page import Page
from .models import FormData, FormElement

logger = logging.getLogger(__name__)

FORM_EXTRACTION_SCRIPT = """
() => {
    const results = [];
    const seen = new Set();

    function getSelector(el) {
        if (el.id) return '#' + el.id;
        if (el.name) return `[name="${el.name}"]`;

        let path = [];
        while (el && el.nodeType === Node.ELEMENT_NODE) {
            let selector = el.nodeName.toLowerCase();
            if (el.id) {
                selector = '#' + el.id;
                path.unshift(selector);
                break;
            }
            let sib = el, nth = 1;
            while (sib = sib.previousElementSibling) {
                if (sib.nodeName === el.nodeName) nth++;
            }
            if (nth > 1) selector += `:nth-of-type(${nth})`;
            path.unshift(selector);
            el = el.parentNode;
        }
        return path.join(' > ');
    }

    function getLabel(el) {
        if (el.id) {
            const label = document.querySelector(`label[for="${el.id}"]`);
            if (label) return label.textContent.trim();
        }
        const parentLabel = el.closest('label');
        if (parentLabel) return parentLabel.textContent.trim();
        if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
        const prev = el.previousElementSibling;
        if (prev && prev.tagName === 'LABEL') return prev.textContent.trim();
        return null;
    }

    const inputs = document.querySelectorAll(
        'input, select, textarea, button[type="submit"]'
    );

    inputs.forEach(el => {
        const selector = getSelector(el);
        if (seen.has(selector)) return;
        seen.add(selector);

        const rect = el.getBoundingClientRect();
        const visible = rect.width > 0 && rect.height > 0;

        if (!visible && el.type !== 'hidden') return;

        const element = {
            selector: selector,
            tag: el.tagName.toLowerCase(),
            type: el.type || null,
            name: el.name || null,
            id: el.id || null,
            label: getLabel(el),
            placeholder: el.placeholder || null,
            value: el.value || null,
            required: el.required || el.getAttribute('aria-required') === 'true',
            visible: visible
        };

        if (el.tagName === 'SELECT') {
            element.options = Array.from(el.options).map(o => o.text);
        }

        results.push(element);
    });

    return results;
}
"""


class FormExtractor:
    """Extracts form elements with their selectors."""

    def __init__(self, page: Page) -> None:
        """Initialize form extractor.

        Args:
            page: Page wrapper instance.
        """
        self._page = page

    def extract(self) -> FormData:
        """Extract all form elements from current page.

        Returns:
            FormData containing all extracted elements.
        """
        logger.info("Extracting form elements...")

        elements = self._page.raw.evaluate(FORM_EXTRACTION_SCRIPT)

        form_elements = [FormElement(**el) for el in elements]
        logger.info(f"Extracted {len(form_elements)} form elements")

        return FormData(
            url=self._page.url,
            title=self._page.raw.title(),
            elements=form_elements,
        )
