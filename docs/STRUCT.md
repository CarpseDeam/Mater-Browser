# Mater-Browser

**Language:** python
**Stack:** Pydantic, Pytest

## Changelog

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

## Stats

- files: 1844
- dirs: 426
- lines: 14830
