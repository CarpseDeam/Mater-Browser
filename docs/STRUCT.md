# Mater-Browser

**Language:** python
**Stack:** Pydantic, Pytest

## Changelog

- **2026-01-26**: Improved form completion detection and payment page filtering
  - Updated `FormProcessor` with additional success URL signals
  - Refined `PageClassifier` to ignore safe job application domains during payment detection
- **2026-01-26**: Improved form processing with scrolling and fallback logic
  - `src/agent/form_processor.py` - Added job description detection, automatic scrolling for "Apply" buttons, and regex-based fallback clicking
- **2026-01-25**: Implemented Similo-inspired PageClassifier for apply button detection
  - `src/agent/page_classifier.py` - New module with batch DOM extraction and weighted scoring
  - `PageType` enum - Classifies pages as EASY_APPLY, EXTERNAL_LINK, ALREADY_APPLIED, CLOSED, LOGIN_REQUIRED, or UNKNOWN
  - `ElementCandidate` dataclass - Stores candidate element attributes and score
  - `PageClassifier` class - Extracts candidates in single JS call, scores using Similo-style weights
  - Refactored `application.py` to use PageClassifier instead of sequential locator chains

## Structure

- `config/` - Configuration
- `docs/` - Documentation
- `scripts/` - Scripts
- `src/` - Source code
  - `agent/`
    - `form_processor.py` - Orchestrates form filling and multi-page flows
    - `success_detector.py` - Detects application completion via URL, text, and form state
    - `page_classifier.py` - Classifies pages and finds primary action buttons
- `assets/` - Static assets

- files: 1844
- dirs: 426
- lines: 14830
