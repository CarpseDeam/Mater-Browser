# Changelog

All notable changes to this project.

- 2026-01-26: feat: Refactor zero-action handling in FormProcessor using ZeroActionsHandler
  - Delegated job description detection, scrolling, and fallback button clicking to `ZeroActionsHandler`
  - Added specific handling for confirmation pages and error pages during the application flow
  - Improved robustness when Claude returns no actions for a given page state
- 2026-01-26: feat: Improve form completion detection and payment page filtering
  - Refactored success detection into new `SuccessDetector` component with URL, text, and form-state signals
  - Implemented `SAFE_URL_PATTERNS` in `PageClassifier` to prevent false positive payment detection on Indeed and LinkedIn apply pages
- 2026-01-26: feat: Add scrolling and fallback "Apply" button logic to `FormProcessor`
  - Implemented job description page detection and automatic scrolling to reveal hidden "Apply" buttons
  - Added regex-based fallback to click "Apply" buttons as a last resort when structured analysis fails

