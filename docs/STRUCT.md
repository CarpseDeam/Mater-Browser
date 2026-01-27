# Mater-Browser

**Language:** python
**Stack:** Pydantic, Pytest

## Structure

- `config/` - Configuration
    - `answers.yaml` - Deterministic answers for form filling
- `docs/` - Documentation
- `scripts/` - Scripts
- `src/` - Source code
    - `agent/`
        - `stuck_detection.py` - Detects and prevents infinite loops in form processing (legacy)
        - `actions.py` - Defines action models and the `ActionPlan` structure (legacy)
        - `models.py` - Application agent models, enums, and constants
        - `answer_engine.py` - Config-driven answer lookup for questions        
        - `linkedin_form_filler.py` - Deterministic filler for LinkedIn Easy Apply
        - `indeed_form_filler.py` - Deterministic filler for Indeed Easy Apply  
        - `indeed_helpers.py` - Specialized helpers for Indeed-specific UI interactions
        - `success_detector.py` - Detects application completion via URL, text, and form state
        - `page_classifier.py` - Classifies pages and finds primary action buttons
    - `executor/`
        - `runner.py` - Manages execution of application plans
    - `feedback/`
        - `failure_logger.py` - Captures and logs application failures for analysis
        - `failure_summarizer.py` - Groups and ranks failures for easier analysis and auto-fixing
        - `config_suggester.py` - Generates structured fix instructions from failure summaries
        - `auto_repairer.py` - Automatically dispatches fixes based on failure thresholds
    - `gui/`
        - `app.py` - Main GUI application setup
        - `dashboard.py` - Primary automation control panel
        - `worker.py` - Background thread for non-blocking browser operations   
    - `profile/` - Profile management and data
- `assets/` - Static assets
- files: 1844
- dirs: 426
- lines: 14830
