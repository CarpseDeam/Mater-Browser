# Changelog

All notable changes to this project.

- 2026-03-02: feat: Add resilience safeguards to LinkedIn Easy Apply flow
  - Implemented hard 120-second timeout for the entire Easy Apply process to prevent hangs
  - Added per-page error handling with a 2-consecutive-error threshold for automatic abortion
  - Introduced `_close_modal` helper to ensure clean state after success, failure, or timeout
  - Added a 30-second timeout to `fill_current_modal` to prevent stalling on complex forms
  - Improved `click_next` resilience with post-click exception handling
  - Fixed application flow ordering by classifying pages before clicking the "Apply" button
  - Added a 3-second timeout to `dismiss_overlays` to prevent blocking the classifier

- 2026-03-02: refactor: Clean up Mater-Browser — Remove all bloat, LinkedIn Easy Apply only
  - Removed all Claude-based form filling infrastructure (`src/agent/claude.py`, `prompts.py`, `actions.py`)
  - Removed Indeed-specific flow and form filling (`src/agent/external_flow.py`, `indeed_form_filler.py`, `indeed_helpers.py`)
  - Deleted obsolete infrastructure including `vision_fallback.py`, `zero_actions_handler.py`, `navigation_helpers.py`, `loop_detector.py`, and `stuck_detection.py`
  - Simplified `ApplicationAgent` and `LinkedInFlow` to focus exclusively on LinkedIn Easy Apply
  - Removed redundant `executor` and `extractor` modules, favoring direct Playwright interaction
  - Streamlined feedback system by removing `auto_repairer.py`, `config_suggester.py`, and `failure_summarizer.py`
  - Cleaned up `models.py` and configuration files to remove Indeed and other dead references
  - Updated `main.py` and GUI components to reflect the LinkedIn-only focus

- 2026-01-31: fix: Fix LinkedIn Easy Apply flow getting stuck immediately
  - Enhanced `LinkedInFlow` with robust modal state hashing (progress bar, aria-valuenow, multiple selectors, element counts, and labels)
  - Improved `LinkedInFormFiller` to support multiple modal selectors (`.artdeco-modal`, `[role="dialog"]`) for broader compatibility
  - Added comprehensive logging for page processing, modal detection, and button interaction
  - Implemented retry logic for the next/submit button and increased stuck detection tolerance
