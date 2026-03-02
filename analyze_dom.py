#!/usr/bin/env python3
"""Analyze LinkedIn DOM dump for selector extraction."""
import json
import sys
from pathlib import Path


def contains_keywords(text: str, keywords: list[str]) -> bool:
    """Check if text contains any of the keywords."""
    if not text:
        return False
    lower = text.lower()
    return any(k in lower for k in keywords)


def analyze_dom_dump(json_path: str) -> None:
    """Extract and print relevant elements from DOM dump."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Get the first page dump
    page = data[0] if isinstance(data, list) else data

    print(f"\n{'='*80}")
    print(f"URL: {page.get('url', 'N/A')}")
    print(f"Title: {page.get('title', 'N/A')}")
    print(f"{'='*80}\n")

    buttons = page.get('buttons', [])
    inputs = page.get('inputs', [])
    selects = page.get('selects', [])
    textareas = page.get('textareas', [])
    modals = page.get('modals', [])
    progress = page.get('progress', [])
    fieldsets = page.get('fieldsets', [])
    labels = page.get('labels', [])

    # 1. Apply buttons
    print("="*80)
    print("1. APPLY BUTTONS")
    print("="*80)
    apply_keywords = ['apply']
    for btn in buttons:
        text = btn.get('text', '')
        aria = btn.get('aria', '')
        classes = btn.get('cls', '')

        if contains_keywords(text, apply_keywords) or contains_keywords(aria, apply_keywords) or contains_keywords(classes, apply_keywords):
            print(f"\nTag: {btn.get('tag')}")
            print(f"Text: '{text}'")
            print(f"Aria-label: '{aria}'")
            print(f"Class: {classes}")
            print(f"Visible: {btn.get('vis')}")
            print(f"Type: {btn.get('type')}")
            print(f"Data-test: {btn.get('dataTest')}")
            print(f"HTML preview: {btn.get('html', '')[:300]}")

    # 2. Modals/Dialogs
    print("\n" + "="*80)
    print("2. MODALS/DIALOGS")
    print("="*80)
    for modal in modals:
        print(f"\nRole: {modal.get('role')}")
        print(f"Class: {modal.get('cls')}")
        print(f"Aria-label: {modal.get('aria')}")
        print(f"Visible: {modal.get('vis')}")

    # 3. Progress indicators
    print("\n" + "="*80)
    print("3. PROGRESS INDICATORS")
    print("="*80)
    for prog in progress:
        print(f"\nTag: {prog.get('tag')}")
        print(f"Class: {prog.get('cls')}")
        print(f"Aria-valuenow: {prog.get('ariaNow')}")
        print(f"Aria-valuemax: {prog.get('ariaMax')}")
        print(f"Visible: {prog.get('vis')}")

    # 4. Navigation buttons
    print("\n" + "="*80)
    print("4. NAVIGATION BUTTONS (next, submit, review, continue, dismiss, close, discard)")
    print("="*80)
    nav_keywords = ['next', 'submit', 'review', 'continue', 'dismiss', 'close', 'discard']
    for btn in buttons:
        text = btn.get('text', '')
        aria = btn.get('aria', '')

        if contains_keywords(text, nav_keywords) or contains_keywords(aria, nav_keywords):
            print(f"\nTag: {btn.get('tag')}")
            print(f"Text: '{text}'")
            print(f"Aria-label: '{aria}'")
            print(f"Class: {btn.get('cls')}")
            print(f"Visible: {btn.get('vis')}")
            print(f"HTML preview: {btn.get('html', '')[:300]}")

    # 5. Form inputs
    print("\n" + "="*80)
    print("5. FORM INPUTS")
    print("="*80)

    print("\n--- INPUTS ---")
    for inp in inputs:
        print(f"\nTag: input")
        print(f"Type: {inp.get('type', 'N/A')}")
        print(f"Name: {inp.get('name', 'N/A')}")
        print(f"ID: {inp.get('id', 'N/A')}")
        print(f"Class: {inp.get('cls', '')}")
        print(f"Aria-label: {inp.get('aria', '')}")
        print(f"Placeholder: {inp.get('placeholder', '')}")
        print(f"Visible: {inp.get('vis')}")

    print("\n--- SELECTS ---")
    for sel in selects:
        print(f"\nTag: select")
        print(f"Name: {sel.get('name', 'N/A')}")
        print(f"ID: {sel.get('id', 'N/A')}")
        print(f"Class: {sel.get('cls', '')}")
        print(f"Aria-label: {sel.get('aria', '')}")
        print(f"Visible: {sel.get('vis')}")

    print("\n--- TEXTAREAS ---")
    for ta in textareas:
        print(f"\nTag: textarea")
        print(f"Name: {ta.get('name', 'N/A')}")
        print(f"ID: {ta.get('id', 'N/A')}")
        print(f"Class: {ta.get('cls', '')}")
        print(f"Aria-label: {ta.get('aria', '')}")
        print(f"Placeholder: {ta.get('placeholder', '')}")
        print(f"Visible: {ta.get('vis')}")

    # 6. Fieldsets with radio buttons
    print("\n" + "="*80)
    print("6. FIELDSETS")
    print("="*80)
    for fs in fieldsets:
        print(f"\nClass: {fs.get('cls')}")
        print(f"Legend: {fs.get('legend', '')}")
        print(f"Visible: {fs.get('vis')}")

    # 7. Form element labels
    print("\n" + "="*80)
    print("7. LABELS (class contains 'form-element' or 'fb-')")
    print("="*80)
    for lbl in labels:
        classes = lbl.get('cls', '')
        if 'form-element' in classes or 'fb-' in classes:
            print(f"\nText: {lbl.get('text', '')}")
            print(f"Class: {classes}")
            print(f"For: {lbl.get('for', '')}")
            print(f"Visible: {lbl.get('vis')}")

    # 8. Key aria-labels
    print("\n" + "="*80)
    print("8. KEY ARIA-LABELS (easy, apply, submit, next, review, dismiss, close)")
    print("="*80)
    aria_keywords = ['easy', 'apply', 'submit', 'next', 'review', 'dismiss', 'close']

    all_elements = buttons + inputs + selects + textareas + labels
    for el in all_elements:
        aria = el.get('aria', '')
        if contains_keywords(aria, aria_keywords):
            print(f"\nTag: {el.get('tag', 'unknown')}")
            print(f"Aria-label: '{aria}'")
            print(f"Class: {el.get('cls', '')}")
            print(f"Text: {el.get('text', '')}")
            print(f"Visible: {el.get('vis')}")

    # Summary stats
    print("\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)
    print(f"Total buttons: {len(buttons)}")
    print(f"Total inputs: {len(inputs)}")
    print(f"Total selects: {len(selects)}")
    print(f"Total textareas: {len(textareas)}")
    print(f"Total modals: {len(modals)}")
    print(f"Total progress: {len(progress)}")
    print(f"Total fieldsets: {len(fieldsets)}")
    print(f"Total labels: {len(labels)}")


if __name__ == '__main__':
    json_path = Path(__file__).parent / 'data' / 'full_dom_dump.json'
    analyze_dom_dump(str(json_path))
