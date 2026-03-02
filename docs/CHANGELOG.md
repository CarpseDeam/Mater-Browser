# Changelog

All notable changes to this project.

- 2026-03-02: refactor: Rewrite LinkedIn apply() to bypass classifier and skip non-Easy-Apply jobs instantly
  - Replaced `PageClassifier` dependency in main `apply()` flow with direct `#jobs-apply-button-id` check
  - Implemented `_handle_non_easy_apply` to instantly skip closed or already applied jobs
  - Added `_dismiss_click_blockers` to remove overlays (messages, cookies, toasts) before clicking
  - Improved modal detection with `_wait_for_modal` supporting multiple 2026-optimized selectors
  - Enhanced `JobQueue` with `in_progress` state tracking to prevent duplicate processing
  - Added `recover_stuck_jobs` to reset `in_progress` jobs on startup or cycle start
  - Fixed duplicate job attempts within a single apply cycle in `AutomationRunner`

- 2026-03-02: feat: Add reliability layer and 2026 DOM support to LinkedIn Easy Apply
  - Implemented automated validation error recovery in `LinkedInFormFiller` to fix and retry failed form steps
  - Added smart resume upload handling to automatically select existing resumes within the modal
  - Introduced stuck recovery mechanism that attempts scrolling and re-filling before aborting
  - Updated all LinkedIn selectors (modal, buttons, progress bars) for stable 2026 DOM structure
  - Added support for typeahead/autocomplete fields in LinkedIn forms
  - Implemented randomized delays between application cycles to mimic human behavior
  - Enhanced clean state management to dismiss existing modals before starting new applications
  - Improved discard confirmation handling when closing modals

- 2026-03-02: docs: Update selector update strategy and project coding standards
  - Expanded LinkedIn DOM analysis scope to include multiple modal dumps
  - Established explicit selector priority: aria-label > role > data-test* > semantic tags > CSS classes
  - Introduced strict coding standards: 25-line function limit, 200-line file limit, and one-level nesting maximum
  - Shifted preference toward functional composition and dataclasses over complex class hierarchies

- 2026-03-02: feat: Add resilience safeguards to LinkedIn Easy Apply flow
  - Implemented hard 120-second timeout for the entire Easy Apply process to prevent hangs
  - Added per-page error handling with a 2-consecutive-error threshold for automatic abortion
  - Introduced _close_modal helper to ensure clean state after success, failure, or timeout
  - Added a 30-second timeout to fill_current_modal to prevent stalling on complex forms
  - Improved click_next resilience with post-click exception handling
  - Fixed application flow ordering by classifying pages before clicking the 'Apply' button
  - Added a 3-second timeout to dismiss_overlays to prevent blocking the classifier

- 2026-03-02: refactor: Clean up Mater-Browser — Remove all bloat, LinkedIn Easy Apply only
  - Removed all Claude-based form filling infrastructure (src/agent/claude.py, prompts.py, actions.py)
  - Removed Indeed-specific flow and form filling (src/agent/external_flow.py, indeed_form_filler.py, indeed_helpers.py)
  - Deleted obsolete infrastructure including vision_fallback.py, zero_actions_handler.py, navigation_helpers.py, loop_detector.py, and stuck_detection.py
  - Simplified ApplicationAgent and LinkedInFlow to focus exclusively on LinkedIn Easy Apply
  - Removed redundant executor and extractor modules, favoring direct Playwright interaction
  - Streamlined feedback system by removing auto_repairer.py, config_suggester.py, and failure_summarizer.py
  - Cleaned up models.py and configuration files to remove Indeed and other dead references
  - Updated main.py and GUI components to reflect the LinkedIn-only focus

- 2026-01-31: fix: Fix LinkedIn Easy Apply flow getting stuck immediately
  - Enhanced LinkedInFlow with robust modal state hashing (progress bar, aria-valuenow, multiple selectors, element counts, and labels)
  - Improved LinkedInFormFiller to support multiple modal selectors (.artdeco-modal, [role='dialog']) for broader compatibility
  - Added comprehensive logging for page processing, modal detection, and button interaction
  - Implemented retry logic for the next/submit button and increased stuck detection tolerance
