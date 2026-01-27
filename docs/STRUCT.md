# Mater-Browser

**Language:** python
**Stack:** Pydantic, Pytest

## Structure

- `config/` - Configuration
    - `answers.yaml` - Deterministic answers for form filling
    - `filters.yaml` - Job filtering and scoring rules
    - `settings.yaml` - General application settings
- `docs/` - Documentation
- `scripts/` - Scripts
- `src/` - Source code
    - `agent/`
        - `application.py` - Core application agent orchestrator
        - `linkedin_flow.py` - Orchestrates LinkedIn Easy Apply automation
        - `external_flow.py` - Orchestrates Indeed Smart Apply automation
        - `linkedin_form_filler.py` - Deterministic filler for LinkedIn Easy Apply
        - `indeed_form_filler.py` - Deterministic filler for Indeed Easy Apply
        - `answer_engine.py` - Config-driven answer lookup for questions
        - `page_classifier.py` - Classifies pages and finds primary action buttons
        - `success_detector.py` - Detects application completion via URL, text, and form state
        - `stuck_detection.py` - Detects and prevents infinite loops in form processing
        - `models.py` - Application agent models, enums, and constants
        - `indeed_helpers.py` - Specialized helpers for Indeed-specific UI interactions
        - `vision_fallback.py` - Vision-based element detection fallback
        - `zero_actions_handler.py` - Handles cases where no actions are identified
    - `executor/`
        - `runner.py` - Manages execution of application plans
    - `feedback/`
        - `failure_logger.py` - Captures and logs application failures for analysis
        - `failure_summarizer.py` - Groups and ranks failures for analysis
        - `config_suggester.py` - Generates fix instructions from failure summaries
        - `auto_repairer.py` - Automatically dispatches fixes based on thresholds
    - `gui/`
        - `app.py` - Main GUI application setup
        - `dashboard.py` - Primary automation control panel
        - `worker.py` - Background thread for browser operations
    - `profile/` - Profile management and data
    - `scraper/` - Job scraping and scoring
        - `jobspy_client.py` - Interface for job scraping
        - `scorer.py` - Job relevance scoring and filtering
- `assets/` - Static assets
- files: 1844
- dirs: 426
- lines: 14830