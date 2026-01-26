# Changelog

All notable changes to this project.

- 2026-01-26: feat: Improve form completion detection and payment page filtering
  - Refactored success detection into new `SuccessDetector` component with URL, text, and form-state signals
  - Implemented `SAFE_URL_PATTERNS` in `PageClassifier` to prevent false positive payment detection on Indeed and LinkedIn apply pages
- 2026-01-26: feat: Add scrolling and fallback "Apply" button logic to `FormProcessor`
  - Implemented job description page detection and automatic scrolling to reveal hidden "Apply" buttons
  - Added regex-based fallback to click "Apply" buttons as a last resort when structured analysis fails

