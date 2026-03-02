"""Dump LinkedIn Easy Apply DOM selectors from a live browser session.

Connects to Chrome via CDP port 9333, navigates to a LinkedIn Easy Apply job,
and dumps all relevant selectors from the job page and Easy Apply modal.

Usage:
    1. Open Chrome with --remote-debugging-port=9333
    2. Log into LinkedIn manually
    3. Run: python dump_selectors.py [job_url]
       (If no URL provided, uses a search results page to find one)
"""
import json
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Page


def dump_page_selectors(page: Page) -> dict:
    """Dump all relevant selectors from the current LinkedIn job page."""
    return page.evaluate('''() => {
        const results = {
            url: window.location.href,
            timestamp: new Date().toISOString(),
            apply_buttons: [],
            modal: null,
            form_elements: [],
            navigation_buttons: [],
            progress_indicators: [],
            confirmation_indicators: [],
            error_indicators: [],
            all_buttons_in_modal: [],
            all_inputs_in_modal: [],
            all_selects_in_modal: [],
            all_textareas_in_modal: [],
            all_fieldsets_in_modal: [],
            all_labels_in_modal: [],
        };

        // Helper to serialize an element
        function serializeEl(el) {
            const rect = el.getBoundingClientRect();
            return {
                tag: el.tagName.toLowerCase(),
                id: el.id || null,
                className: el.className || null,
                type: el.type || null,
                name: el.name || null,
                role: el.getAttribute('role'),
                ariaLabel: el.getAttribute('aria-label'),
                ariaDescribedby: el.getAttribute('aria-describedby'),
                ariaRequired: el.getAttribute('aria-required'),
                dataTestId: el.getAttribute('data-testid'),
                dataTest: el.getAttribute('data-test') || [...el.attributes].filter(a => a.name.startsWith('data-test')).map(a => `${a.name}=${a.value}`).join(', '),
                text: el.textContent?.trim().substring(0, 100),
                value: el.value || null,
                placeholder: el.placeholder || null,
                href: el.href || null,
                visible: rect.width > 0 && rect.height > 0,
                rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
            };
        }

        // 1. Find ALL apply-related buttons on the page
        const applySelectors = [
            'button.jobs-apply-button',
            'button[aria-label*="Easy Apply"]',
            'button[aria-label*="Apply"]',
            'button.jobs-apply-button--top-card',
            '[data-testid*="apply"]',
            'button[data-control-name*="apply"]',
            'button[class*="jobs-apply"]',
            '.jobs-apply-button',
            '[class*="apply-button"]',
        ];
        const seenApply = new Set();
        for (const sel of applySelectors) {
            document.querySelectorAll(sel).forEach(el => {
                const key = el.outerHTML.substring(0, 200);
                if (!seenApply.has(key)) {
                    seenApply.add(key);
                    results.apply_buttons.push({
                        selector_matched: sel,
                        ...serializeEl(el),
                        outerHTML: el.outerHTML.substring(0, 500),
                    });
                }
            });
        }

        // 2. Find the modal
        const modalSelectors = [
            '.jobs-easy-apply-modal',
            '.artdeco-modal',
            '[data-test-modal]',
            '[role="dialog"]',
            '.jobs-easy-apply-content',
        ];
        for (const sel of modalSelectors) {
            const modal = document.querySelector(sel);
            if (modal && modal.offsetParent !== null) {
                results.modal = {
                    selector: sel,
                    className: modal.className,
                    id: modal.id,
                    role: modal.getAttribute('role'),
                    ariaLabel: modal.getAttribute('aria-label'),
                    childCount: modal.children.length,
                    innerHTML_preview: modal.innerHTML.substring(0, 300),
                };

                // 3. Dump ALL form-related elements inside modal
                modal.querySelectorAll('button').forEach(el => {
                    results.all_buttons_in_modal.push({
                        ...serializeEl(el),
                        outerHTML: el.outerHTML.substring(0, 300),
                    });
                });

                modal.querySelectorAll('input').forEach(el => {
                    results.all_inputs_in_modal.push(serializeEl(el));
                });

                modal.querySelectorAll('select').forEach(el => {
                    const options = [...el.options].map(o => ({ value: o.value, text: o.text, selected: o.selected }));
                    results.all_selects_in_modal.push({ ...serializeEl(el), options });
                });

                modal.querySelectorAll('textarea').forEach(el => {
                    results.all_textareas_in_modal.push(serializeEl(el));
                });

                modal.querySelectorAll('fieldset').forEach(el => {
                    const legend = el.querySelector('legend')?.textContent?.trim();
                    const radios = [...el.querySelectorAll('input[type="radio"]')].map(r => ({
                        value: r.value,
                        checked: r.checked,
                        label: r.labels?.[0]?.textContent?.trim(),
                        id: r.id,
                    }));
                    results.all_fieldsets_in_modal.push({
                        ...serializeEl(el),
                        legend,
                        radios,
                        dataTest: [...el.attributes].filter(a => a.name.startsWith('data-test')).map(a => `${a.name}=${a.value}`).join(', '),
                    });
                });

                modal.querySelectorAll('label, .fb-form-element-label, [class*="form-element-label"]').forEach(el => {
                    const forAttr = el.getAttribute('for');
                    results.all_labels_in_modal.push({
                        text: el.textContent?.trim().substring(0, 200),
                        for: forAttr,
                        className: el.className,
                        tag: el.tagName.toLowerCase(),
                    });
                });

                // 4. Progress indicators
                modal.querySelectorAll('progress, [role="progressbar"], .artdeco-completeness-meter, [class*="progress"]').forEach(el => {
                    results.progress_indicators.push({
                        ...serializeEl(el),
                        ariaValueNow: el.getAttribute('aria-valuenow'),
                        ariaValueMax: el.getAttribute('aria-valuemax'),
                        value: el.value,
                        max: el.max,
                    });
                });

                break; // Use first visible modal
            }
        }

        // 5. Confirmation / success indicators (check whole page)
        const confirmSelectors = [
            '[class*="post-apply"]',
            '[data-test-modal-id*="post-apply"]',
            '.artdeco-modal__header',
        ];
        for (const sel of confirmSelectors) {
            document.querySelectorAll(sel).forEach(el => {
                results.confirmation_indicators.push({
                    selector: sel,
                    ...serializeEl(el),
                });
            });
        }

        // Check for success text patterns
        const pageText = document.body.innerText.toLowerCase();
        const successPatterns = ['application sent', 'your application was sent', 'application submitted', 'successfully applied'];
        results.success_text_found = successPatterns.filter(p => pageText.includes(p));

        // 6. Error indicators
        const errorSelectors = [
            '.artdeco-inline-feedback',
            '.artdeco-inline-feedback__message',
            '[class*="error"]',
            '[class*="validation"]',
        ];
        for (const sel of errorSelectors) {
            document.querySelectorAll(sel).forEach(el => {
                if (el.offsetParent && el.textContent?.trim()) {
                    results.error_indicators.push({
                        selector: sel,
                        text: el.textContent?.trim().substring(0, 200),
                        className: el.className,
                    });
                }
            });
        }

        // 7. Form sections/groupings
        const sectionSelectors = [
            '.jobs-easy-apply-form-section__grouping',
            '.jobs-easy-apply-form-element',
            '.fb-form-element',
            '[class*="form-section"]',
            '[class*="form-element"]',
        ];
        const seenSections = new Set();
        for (const sel of sectionSelectors) {
            document.querySelectorAll(sel).forEach(el => {
                if (el.offsetParent) {
                    const key = el.className + el.textContent?.substring(0, 50);
                    if (!seenSections.has(key)) {
                        seenSections.add(key);
                        results.form_elements.push({
                            selector: sel,
                            className: el.className,
                            text_preview: el.textContent?.trim().substring(0, 150),
                            inputCount: el.querySelectorAll('input').length,
                            selectCount: el.querySelectorAll('select').length,
                            textareaCount: el.querySelectorAll('textarea').length,
                        });
                    }
                }
            });
        }

        return results;
    }''')


def main():
    job_url = sys.argv[1] if len(sys.argv) > 1 else None

    print("Connecting to Chrome on CDP port 9333...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
        
        # Find the LinkedIn tab
        page = None
        for context in browser.contexts:
            for p_tab in context.pages:
                url = p_tab.url
                print(f"  Found tab: {url[:80]}")
                if "linkedin.com" in url:
                    page = p_tab
        
        if not page:
            print("ERROR: No LinkedIn tab found. Open a LinkedIn job page in this Chrome window first.")
            browser.close()
            return
        
        print(f"  Using tab: {page.url[:100]}")

        if job_url:
            print(f"Navigating to: {job_url}")
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=15000)
            except Exception as e:
                if "err_aborted" not in str(e).lower():
                    print(f"Navigation error: {e}")
            time.sleep(3)

        # PHASE 1: Dump the job page (before clicking Easy Apply)
        print("\n=== PHASE 1: Job Page Selectors ===")
        page_dump = dump_page_selectors(page)

        output_path = Path("data/selector_dump_page.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(page_dump, f, indent=2)
        print(f"Page dump saved to: {output_path}")
        print(f"  Apply buttons found: {len(page_dump['apply_buttons'])}")
        print(f"  Modal found: {page_dump['modal'] is not None}")

        # Print apply button details
        for btn in page_dump['apply_buttons']:
            print(f"  APPLY BTN: text='{btn.get('text', '')[:60]}' aria='{btn.get('ariaLabel', '')}' selector='{btn['selector_matched']}'")

        # PHASE 2: Click the Easy Apply button, then dump the modal
        if page_dump['apply_buttons']:
            print("\n=== PHASE 2: Clicking Easy Apply Button ===")
            # Try direct selectors first
            clicked = False
            for sel in [
                'button.jobs-apply-button',
                'button[aria-label*="Easy Apply"]',
                'button[class*="jobs-apply"]',
            ]:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=1000):
                        btn.click()
                        clicked = True
                        print(f"  Clicked: {sel}")
                        break
                except Exception:
                    continue

            if clicked:
                time.sleep(2)
                print("\n=== PHASE 3: Modal Selectors ===")
                modal_dump = dump_page_selectors(page)

                output_path2 = Path("data/selector_dump_modal.json")
                with open(output_path2, "w") as f:
                    json.dump(modal_dump, f, indent=2)
                print(f"Modal dump saved to: {output_path2}")
                print(f"  Modal found: {modal_dump['modal'] is not None}")
                print(f"  Buttons in modal: {len(modal_dump['all_buttons_in_modal'])}")
                print(f"  Inputs in modal: {len(modal_dump['all_inputs_in_modal'])}")
                print(f"  Selects in modal: {len(modal_dump['all_selects_in_modal'])}")
                print(f"  Textareas in modal: {len(modal_dump['all_textareas_in_modal'])}")
                print(f"  Fieldsets in modal: {len(modal_dump['all_fieldsets_in_modal'])}")
                print(f"  Labels in modal: {len(modal_dump['all_labels_in_modal'])}")
                print(f"  Progress bars: {len(modal_dump['progress_indicators'])}")
                print(f"  Errors visible: {len(modal_dump['error_indicators'])}")

                # Print button details
                print("\n  --- Modal Buttons ---")
                for btn in modal_dump['all_buttons_in_modal']:
                    vis = "VISIBLE" if btn.get('visible') else "hidden"
                    print(f"    [{vis}] text='{btn.get('text', '')[:60]}' aria='{btn.get('ariaLabel', '')}' class='{str(btn.get('className', ''))[:80]}'")

                # Print labels
                print("\n  --- Modal Labels ---")
                for lbl in modal_dump['all_labels_in_modal']:
                    print(f"    text='{lbl.get('text', '')[:80]}' class='{lbl.get('className', '')[:60]}'")

                # Print progress
                print("\n  --- Progress Indicators ---")
                for prog in modal_dump['progress_indicators']:
                    print(f"    role='{prog.get('role', '')}' value={prog.get('ariaValueNow', prog.get('value', '?'))} max={prog.get('ariaValueMax', prog.get('max', '?'))} class='{str(prog.get('className', ''))[:60]}'")

            else:
                print("  Could not click any apply button")
        else:
            print("\nNo apply buttons found on page")

        browser.close()
        print("\nDone!")


if __name__ == "__main__":
    main()
