"""Nuclear option: dump EVERYTHING from every tab."""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    print("Connecting...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")

        all_results = []

        for ci, context in enumerate(browser.contexts):
            for pi, page in enumerate(context.pages):
                url = page.url
                print(f"\nTab [{ci}][{pi}]: {url}")

                try:
                    html = page.content()
                    print(f"  HTML length: {len(html)}")

                    dump = page.evaluate('''() => {
                        function ser(el) {
                            try {
                                return {
                                    tag: el.tagName?.toLowerCase(),
                                    id: el.id || null,
                                    cls: el.className?.toString?.()?.substring(0, 200) || null,
                                    role: el.getAttribute('role'),
                                    aria: el.getAttribute('aria-label'),
                                    text: el.textContent?.trim()?.substring(0, 120),
                                    type: el.type || null,
                                    name: el.name || null,
                                    href: el.href || null,
                                    vis: el.offsetParent !== null || el.offsetWidth > 0,
                                    dataTest: [...el.attributes].filter(a => a.name.startsWith('data-test')).map(a => a.name + '=' + a.value).join(', ') || null,
                                    html: el.outerHTML?.substring(0, 400),
                                };
                            } catch(e) { return {error: e.message}; }
                        }

                        const r = {
                            url: location.href,
                            title: document.title,
                            buttons: [],
                            inputs: [],
                            selects: [],
                            textareas: [],
                            fieldsets: [],
                            labels: [],
                            modals: [],
                            progress: [],
                            forms: [],
                            anchors_apply: [],
                            all_aria_labels: [],
                        };

                        document.querySelectorAll('button').forEach(el => r.buttons.push(ser(el)));
                        document.querySelectorAll('input').forEach(el => r.inputs.push(ser(el)));
                        document.querySelectorAll('select').forEach(el => {
                            const s = ser(el);
                            s.options = [...el.options].map(o => ({v: o.value, t: o.text, sel: o.selected}));
                            r.selects.push(s);
                        });
                        document.querySelectorAll('textarea').forEach(el => r.textareas.push(ser(el)));
                        document.querySelectorAll('fieldset').forEach(el => {
                            const s = ser(el);
                            s.radios = [...el.querySelectorAll('input[type=radio]')].map(radio => ({
                                val: radio.value,
                                checked: radio.checked,
                                label: radio.labels?.[0]?.textContent?.trim()?.substring(0, 80),
                                id: radio.id,
                            }));
                            r.fieldsets.push(s);
                        });
                        document.querySelectorAll('label, [class*="label"]').forEach(el => {
                            if (el.textContent?.trim()) {
                                r.labels.push({
                                    tag: el.tagName?.toLowerCase(),
                                    cls: el.className?.toString?.()?.substring(0, 150) || null,
                                    for: el.getAttribute('for'),
                                    text: el.textContent?.trim()?.substring(0, 200),
                                });
                            }
                        });
                        document.querySelectorAll('[role="dialog"], [role="alertdialog"], .artdeco-modal, [class*="modal"], [class*="overlay"]').forEach(el => {
                            r.modals.push(ser(el));
                        });
                        document.querySelectorAll('progress, [role="progressbar"], [class*="progress"]').forEach(el => {
                            const s = ser(el);
                            s.value = el.value;
                            s.max = el.max;
                            s.ariaNow = el.getAttribute('aria-valuenow');
                            s.ariaMax = el.getAttribute('aria-valuemax');
                            r.progress.push(s);
                        });
                        document.querySelectorAll('form').forEach(el => r.forms.push(ser(el)));
                        document.querySelectorAll('a').forEach(el => {
                            if ((el.textContent || '').toLowerCase().includes('apply')) {
                                r.anchors_apply.push(ser(el));
                            }
                        });
                        document.querySelectorAll('[aria-label]').forEach(el => {
                            r.all_aria_labels.push({
                                tag: el.tagName?.toLowerCase(),
                                aria: el.getAttribute('aria-label'),
                                cls: el.className?.toString?.()?.substring(0, 100) || null,
                                vis: el.offsetParent !== null,
                            });
                        });

                        return r;
                    }''')

                    all_results.append(dump)

                    print(f"  Buttons: {len(dump['buttons'])}")
                    print(f"  Inputs: {len(dump['inputs'])}")
                    print(f"  Selects: {len(dump['selects'])}")
                    print(f"  Modals: {len(dump['modals'])}")
                    print(f"  Forms: {len(dump['forms'])}")
                    print(f"  Aria labels: {len(dump['all_aria_labels'])}")

                except Exception as e:
                    print(f"  ERROR: {e}")
                    all_results.append({"url": url, "error": str(e)})

        out = Path("data/full_dom_dump.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)

        print(f"\n=== DONE === Saved to {out} ({out.stat().st_size} bytes)")
        browser.close()


if __name__ == "__main__":
    main()
