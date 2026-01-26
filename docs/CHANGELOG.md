# Changelog

All notable changes to this project.

- 2026-01-26: refactor: Replace hardcoded timeout with PAGE_LOAD_TIMEOUT_MS in LinkedInFlow
- 2026-01-26: feat: Enhance robustness with plan validation, navigation retries, and intercept handling
  - Added ActionPlan validation in `ClaudeAgent` to ensure AI actions match element types
  - Implemented retry logic for `Page.goto` with automated error handling for aborted navigations
  - Enhanced `ActionRunner` to handle intercepted clicks by dismissing overlays and retrying
  - Centralized and updated timeout and retry constants in `src/agent/models.py`
  - Improved loop detection logic in `FormProcessor` by recording state after action execution

- 2026-01-26: fix: Handle external LinkedIn popups and improve upload action robustness
  - Updated `LinkedInFlow` to immediately navigate to captured popups for external jobs, avoiding 30s timeouts
  - Enhanced `ActionRunner`'s `UploadAction` to correctly resolve `<label>` targets to their associated `<input type="file">`
  - Added Dice modal dismissal to `PageClassifier`'s overlay cleanup logic
  - Refactored `PageClassifier` account creation check for better efficiency

- 2026-01-26: refactor: Enhance PageClassifier detection and click robustness
  - Improved `EXTERNAL_LINK` detection by checking ARIA labels, roles, and button text patterns
  - Refactored apply button classification into specialized `_classify_apply_button` logic
  - Enhanced `click_apply_button` with a generator-based retry sequence (`_click_attempts`)
  - Optimized DOM overlay dismissal and login detection logic

- 2026-01-26: feat: Enhance form interaction robustness and success detection
  - Added rate limiting and click limits to Indeed modal dismissal in IndeedHelpers
  - Improved SuccessDetector accuracy by tracking if forms were actually filled before detecting disappearance
  - Enhanced ActionRunner to handle hidden radio and checkbox inputs by clicking associated labels
  - Added reset logic to FormProcessor to ensure clean state between application attempts

- 2026-01-26: refactor: Centralize filter configuration and enhance JobScorer
  - Introduced `FilterConfig` for externalized and manageable filter rules (YAML-based)
  - Refactored `JobScorer` to use `FilterConfig` for title exclusions, stack exclusions, role exclusions, and scoring weights
  - Added `FilterStats` and `FilterResult` for detailed tracking and logging of filtering reasons
  - Updated `AutomationRunner` to use the new `check_filter` API for more descriptive skipping reasons
- 2026-01-26: feat: Enhance job scoring and filtering logic in JobScorer
  - Added `TITLE_HARD_EXCLUSIONS` for immediate filtering of non-relevant roles (Senior/Lead, Mobile, DevOps, etc.)
  - Expanded `STACK_EXCLUSIONS` to include Cloud, IoT, and non-Python languages (Java, Rust)
  - Implemented strict Python keyword check in job title and early description
- 2026-01-26: feat: Refactor zero-action handling in FormProcessor using ZeroActionsHandler
  - Delegated job description detection, scrolling, and fallback button clicking to `ZeroActionsHandler`
  - Integrated `VisionFallback` to use Claude's vision capabilities for finding "Apply" buttons when DOM analysis fails
  - Added support for `ANTHROPIC_API_KEY` to enable vision-based element detection
  - Added specific handling for confirmation pages and error pages during the application flow
  - Improved robustness when Claude returns no actions for a given page state
- 2026-01-26: feat: Improve form completion detection and payment page filtering
  - Refactored success detection into new `SuccessDetector` component with URL, text, and form-state signals
  - Implemented `SAFE_URL_PATTERNS` in `PageClassifier` to prevent false positive payment detection on Indeed and LinkedIn apply pages
- 2026-01-26: feat: Add scrolling and fallback "Apply" button logic to `FormProcessor`
  - Implemented job description page detection and automatic scrolling to reveal hidden "Apply" buttons
  - Added regex-based fallback to click "Apply" buttons as a last resort when structured analysis fails