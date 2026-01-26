// buildDomTree.js - Extracts interactive elements with unique indices
// Based on browser-use approach (MIT license)

(function buildDomTree(options = {}) {
    const {
        doHighlightElements = false,
        viewportExpansion = 0,
    } = options;

    const interactiveElements = new Set([
        'a', 'button', 'input', 'select', 'textarea',
        'details', 'summary', 'option', 'label'
    ]);

    const interactiveRoles = new Set([
        'button', 'link', 'checkbox', 'radio', 'textbox',
        'combobox', 'listbox', 'menu', 'menuitem', 'option',
        'searchbox', 'slider', 'spinbutton', 'switch', 'tab'
    ]);

    let elementIndex = 0;
    const selectorMap = {};
    const elements = [];

    function getSelector(el) {
        if (el.id) return `#${CSS.escape(el.id)}`;
        if (el.name) return `[name="${CSS.escape(el.name)}"]`;

        const path = [];
        let current = el;
        while (current && current !== document.body) {
            let selector = current.tagName.toLowerCase();
            if (current.id) {
                path.unshift(`#${CSS.escape(current.id)}`);
                break;
            }
            const siblings = current.parentElement?.children || [];
            const sameTag = Array.from(siblings).filter(s => s.tagName === current.tagName);
            if (sameTag.length > 1) {
                const idx = sameTag.indexOf(current) + 1;
                selector += `:nth-of-type(${idx})`;
            }
            path.unshift(selector);
            current = current.parentElement;
        }
        return path.join(' > ');
    }

    function getLabel(el) {
        if (el.id) {
            const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
            if (label) return label.textContent.trim();
        }
        const parent = el.closest('label');
        if (parent) {
            const clone = parent.cloneNode(true);
            clone.querySelectorAll('input, select, textarea').forEach(c => c.remove());
            return clone.textContent.trim();
        }
        if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
        if (el.getAttribute('aria-labelledby')) {
            const labelEl = document.getElementById(el.getAttribute('aria-labelledby'));
            if (labelEl) return labelEl.textContent.trim();
        }
        if (el.placeholder) return el.placeholder;
        if (el.title) return el.title;
        const prev = el.previousSibling;
        if (prev && prev.nodeType === Node.TEXT_NODE) {
            const text = prev.textContent.trim();
            if (text) return text;
        }
        return null;
    }

    function hasPointerEventsNone(el) {
        let current = el;
        while (current && current !== document.body) {
            const style = window.getComputedStyle(current);
            if (style.pointerEvents === 'none') return true;
            current = current.parentElement;
        }
        return false;
    }

    function isCoveredByOverlay(el) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return false;

        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const topEl = document.elementFromPoint(centerX, centerY);

        if (!topEl || el.contains(topEl) || topEl.contains(el)) return false;

        const topStyle = window.getComputedStyle(topEl);
        const isOverlay = topStyle.position === 'fixed' || topStyle.position === 'absolute';
        return isOverlay;
    }

    function isVisible(el) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        if (parseFloat(style.opacity) === 0) return false;
        if (hasPointerEventsNone(el)) return false;
        if (isCoveredByOverlay(el)) return false;
        return true;
    }

    function isInteractive(el) {
        const tag = el.tagName.toLowerCase();
        if (interactiveElements.has(tag)) return true;

        const role = el.getAttribute('role');
        if (role && interactiveRoles.has(role)) return true;

        const style = window.getComputedStyle(el);
        if (style.cursor === 'pointer') return true;

        if (el.isContentEditable) return true;

        if (el.hasAttribute('tabindex') && el.tabIndex >= 0) return true;

        if (el.onclick || el.getAttribute('onclick')) return true;

        return false;
    }

    function processElement(el) {
        if (!isVisible(el)) return;
        if (!isInteractive(el)) return;

        const idx = elementIndex++;
        const ref = `@e${idx}`;
        const selector = getSelector(el);
        const tag = el.tagName.toLowerCase();

        const element = {
            ref: ref,
            index: idx,
            tag: tag,
            type: el.type || null,
            name: el.name || null,
            id: el.id || null,
            selector: selector,
            label: getLabel(el),
            placeholder: el.placeholder || null,
            value: el.value || null,
            text: el.textContent?.trim().substring(0, 100) || null,
            required: el.required || el.getAttribute('aria-required') === 'true',
            disabled: el.disabled || el.getAttribute('aria-disabled') === 'true',
        };

        if (tag === 'select') {
            element.options = Array.from(el.options).map(o => ({
                value: o.value,
                text: o.text,
                selected: o.selected
            }));
        }

        if (tag === 'button' || (tag === 'input' && ['submit', 'button'].includes(el.type))) {
            element.buttonText = el.value || el.textContent?.trim() || null;
        }

        if (tag === 'a') {
            element.href = el.href || null;
        }

        if (doHighlightElements) {
            el.setAttribute('data-mater-ref', ref);
            el.style.outline = '2px solid red';

            const overlay = document.createElement('div');
            overlay.textContent = ref;
            overlay.style.cssText = `
                position: absolute;
                background: red;
                color: white;
                font-size: 10px;
                padding: 1px 3px;
                z-index: 99999;
                pointer-events: none;
            `;
            const rect = el.getBoundingClientRect();
            overlay.style.top = `${rect.top + window.scrollY}px`;
            overlay.style.left = `${rect.left + window.scrollX}px`;
            document.body.appendChild(overlay);
        }

        selectorMap[ref] = selector;
        elements.push(element);
    }

    document.querySelectorAll('*').forEach(processElement);

    return {
        url: window.location.href,
        title: document.title,
        elementCount: elements.length,
        elements: elements,
        selectorMap: selectorMap
    };
})
