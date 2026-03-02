# LinkedIn Selector Update Action Plan

## Problem

The current DOM dump (`data/full_dom_dump.json`) is from a **job search results page**, not from inside an Easy Apply modal. We cannot validate or update the Easy Apply selectors without the correct DOM data.

## Solution: Capture Easy Apply Modal DOM

### Step 1: Prepare Chrome with Remote Debugging

```bash
# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9333 --user-data-dir="C:\ChromeProfile"

# Mac
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9333 --user-data-dir="/tmp/ChromeProfile"

# Linux
google-chrome --remote-debugging-port=9333 --user-data-dir="/tmp/ChromeProfile"
```

### Step 2: Log into LinkedIn

1. In the Chrome window, navigate to linkedin.com
2. Log in with your credentials
3. Navigate to Jobs search

### Step 3: Capture DOM from Easy Apply Modal

**Option A: Automated capture (recommended)**

```bash
cd C:\Projects\Mater-Browser

# This will:
# - Find your LinkedIn tab
# - Navigate to the job
# - Dump page selectors
# - Click Easy Apply
# - Dump modal selectors
python dump_selectors.py https://www.linkedin.com/jobs/view/JOBID

# Replace JOBID with an actual Easy Apply job ID
```

**Option B: Manual capture for multiple pages**

```bash
# Step through the flow manually and capture at each step
python dump_selectors.py  # Captures current tab state

# Then manually:
# 1. Click Easy Apply
# 2. Run: python dump_selectors.py
# 3. Fill one page, click Next
# 4. Run: python dump_selectors.py
# 5. Repeat for each page
```

Expected output files:
- `data/selector_dump_page.json` — Job page before clicking Easy Apply
- `data/selector_dump_modal.json` — Easy Apply modal after clicking

### Step 4: Analyze the Captured Data

```bash
# Re-run the analysis with the new modal dump
python analyze_dom.py

# Or create a specific modal analyzer
python -c "
import json
from pathlib import Path

modal_dump = json.load(open('data/selector_dump_modal.json'))

print('=== MODAL ANALYSIS ===')
print(f'Modal found: {modal_dump[\"modal\"] is not None}')
print(f'Buttons: {len(modal_dump[\"all_buttons_in_modal\"])}')
print(f'Inputs: {len(modal_dump[\"all_inputs_in_modal\"])}')
print(f'Selects: {len(modal_dump[\"all_selects_in_modal\"])}')
print(f'Textareas: {len(modal_dump[\"all_textareas_in_modal\"])}')
print(f'Fieldsets: {len(modal_dump[\"all_fieldsets_in_modal\"])}')
print(f'Labels: {len(modal_dump[\"all_labels_in_modal\"])}')

print('\n=== MODAL CONTAINER ===')
if modal_dump['modal']:
    print(f'Selector: {modal_dump[\"modal\"][\"selector\"]}')
    print(f'Class: {modal_dump[\"modal\"][\"className\"]}')
    print(f'Role: {modal_dump[\"modal\"][\"role\"]}')

print('\n=== NAVIGATION BUTTONS ===')
for btn in modal_dump['all_buttons_in_modal']:
    text = btn.get('text', '')[:60]
    aria = btn.get('ariaLabel', '')[:60]
    if any(kw in text.lower() or kw in aria.lower() for kw in ['next', 'submit', 'review', 'continue']):
        print(f'[{\"VIS\" if btn.get(\"visible\") else \"HID\"}] text=\"{text}\" aria=\"{aria}\"')
"
```

### Step 5: Update Code Selectors

Based on the modal dump analysis, update these files:

#### `src/agent/page_classifier.py`

```python
# Line 37-43: Update LINKEDIN_EASY_APPLY_SELECTORS
LINKEDIN_EASY_APPLY_SELECTORS = [
    # PUT NEW WORKING SELECTORS FROM DOM DUMP FIRST
    'button[aria-label*="Easy Apply"]',  # if this pattern still works
    'button.jobs-apply-button',  # fallback
    'button[data-control-name="jobdetails_topcard_inapply"]',  # fallback
    # Add new selectors from modal dump here
]
```

#### `src/agent/linkedin_form_filler.py`

```python
# Line 107-112: Update modal selectors
modal_selectors = [
    # PUT NEW WORKING SELECTORS FROM DOM DUMP FIRST
    ".jobs-easy-apply-modal",  # might still work
    ".artdeco-modal",  # fallback
    '[role="dialog"]',  # fallback
    # Add new selectors from modal dump here
]

# Line 80-93: Update SUBMIT_BUTTON_PATTERNS
SUBMIT_BUTTON_PATTERNS = [
    # PUT NEW WORKING SELECTORS FROM DOM DUMP FIRST
    'button[aria-label="Submit application"]',
    'button[aria-label*="Submit" i]',
    'button[aria-label*="Review" i]',
    'button[aria-label*="Next" i]',
    # Add new patterns from modal dump here
]

# Update LinkedInSelectors class (line 18-75)
class LinkedInSelectors:
    # Update each selector based on modal dump
    FORM_SECTION = ".jobs-easy-apply-form-section__grouping"  # UPDATE IF CHANGED
    FORM_ELEMENT = ".jobs-easy-apply-form-element"  # UPDATE IF CHANGED
    TEXT_INPUT = ".artdeco-text-input--input"  # UPDATE IF CHANGED
    # ... etc
```

#### `src/agent/linkedin_flow.py`

```python
# Line 154-158: Update dismiss selectors
dismiss_selectors = [
    # PUT NEW WORKING SELECTORS FROM DOM DUMP FIRST
    'button[aria-label="Dismiss"]',  # this one likely still works
    '[data-test-modal-close-btn]',
    'button.artdeco-modal__dismiss',
    # Add new selectors from modal dump here
]

# Line 307-312: Update modal selectors for hash
modal_selectors = [
    # PUT NEW WORKING SELECTORS FROM DOM DUMP FIRST
    ".jobs-easy-apply-modal",
    ".artdeco-modal",
    "[role='dialog']",
    # Add new selectors from modal dump here
]
```

### Step 6: Test the Updates

```bash
# Run the agent on a single Easy Apply job
python src/cli.py --max-applications 1

# Watch the logs for:
# - "Found modal with selector: X" ✅
# - "No Easy Apply modal found" ❌
# - "Clicked button: X" ✅
# - "No next/submit button found" ❌
```

### Step 7: Document Findings

Update `MEMORY.md` with:
- Date of selector update
- Which selectors changed
- Which selectors still work
- Any new patterns discovered

## Common LinkedIn Selector Patterns

LinkedIn frequently changes class names but tends to keep:

✅ **Stable (usually don't change):**
- `aria-label` attributes
- `role` attributes
- `data-test*` attributes
- Element structure (modals, forms, fieldsets)

❌ **Unstable (change often):**
- CSS class names (e.g., `.jobs-apply-button` → `.jobs-unified-top-card__button-apply`)
- Specific data attributes (e.g., `data-control-name` values)

## Troubleshooting

### Issue: `dump_selectors.py` can't find LinkedIn tab

**Solution:** Make sure Chrome is running with `--remote-debugging-port=9333` and you're logged into LinkedIn

### Issue: No modal found after clicking Easy Apply

**Possible causes:**
1. Not an Easy Apply job (external application)
2. Already applied to this job
3. LinkedIn blocked/rate-limited you
4. Modal selector changed

**Debug:**
```bash
# Check what's visible on the page
python -c "
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp('http://127.0.0.1:9333')
    page = browser.contexts[0].pages[0]

    # Find all modals
    modals = page.locator('[role=\"dialog\"]').all()
    print(f'Found {len(modals)} modals')

    for i, modal in enumerate(modals):
        if modal.is_visible():
            print(f'Modal {i}: visible')
            print(f'  Class: {modal.get_attribute(\"class\")}')
            print(f'  Aria-label: {modal.get_attribute(\"aria-label\")}')
"
```

### Issue: Form elements not being filled

**Possible causes:**
1. Field selectors changed
2. LinkedIn added new field types
3. Timing issues (form not loaded yet)

**Debug:** Check the modal dump for actual classes used:
```bash
python -c "
import json
dump = json.load(open('data/selector_dump_modal.json'))
print('Input classes:')
for inp in dump['all_inputs_in_modal'][:5]:
    print(f'  {inp.get(\"className\", \"\")}')
"
```

## Timeline

- **Days 1-2:** Capture modal DOM dumps from multiple Easy Apply jobs
- **Day 3:** Analyze dumps and identify new selectors
- **Day 4:** Update code with new selectors
- **Day 5:** Test and validate on 10+ jobs
- **Day 6:** Deploy and monitor

## Success Criteria

✅ Modal detection rate > 95%
✅ Form fill success rate > 90%
✅ Button click success rate > 95%
✅ Zero false positives (applying to wrong jobs)
✅ Proper handling of confirmation pages

---

**Current Status:** ⏸️ BLOCKED - Need Easy Apply modal DOM dump

**Next Action:** Capture modal DOM using `dump_selectors.py`
