# Changelog

All notable changes to this project.

- 2026-01-26: feat: Improve form completion detection and payment page filtering
  - Added "confirmation" to positive URL signals in `FormProcessor`
  - Implemented `SAFE_URL_PATTERNS` in `PageClassifier` to prevent false positive payment detection on Indeed and LinkedIn apply pages
- 2026-01-26: feat: Add scrolling and fallback "Apply" button logic to `FormProcessor`
  - Implemented job description page detection
  - Added scrolling behavior to find "Apply" buttons when no initial actions are detected
  - Added regex-based fallback to click "Apply" buttons as a last resort

