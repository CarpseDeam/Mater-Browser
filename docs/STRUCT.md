# Mater-Browser

**Language:** python
**Stack:** Playwright, Pydantic, Pytest

## Structure

- `config/` - Configuration
    - `answers.yaml` - Deterministic answers for form filling
    - `filters.yaml` - Job filtering and scoring rules
    - `settings.yaml` - General application settings
- `docs/` - Documentation
- `scripts/` - Utility scripts
- `src/` - Source code
    - `agent/`
        - `application.py` - Core application agent orchestrator
        - `linkedin_flow.py` - Orchestrates LinkedIn Easy Apply automation
        - `linkedin_form_filler.py` - Deterministic filler for LinkedIn Easy Apply
        - `answer_engine.py` - Config-driven answer lookup for questions
        - `page_classifier.py` - Classifies pages and finds primary action buttons
        - `dom_extractor.py` - Candidate extraction for button detection
        - `visibility_helpers.py` - Helpers for element visibility and interaction
        - `models.py` - Application agent models, enums, and constants
    - `browser/`
        - `connection.py` - Playwright browser connection management
        - `page.py` - Page wrapper with convenience methods
        - `tabs.py` - Tab and popup management
    - `core/`
        - `config.py` - Settings and configuration loading
        - `logging.py` - Logging setup and utilities
    - `feedback/`
        - `failure_logger.py` - Captures unknown questions and failures
    - `gui/`
        - `app.py` - Main GUI application setup
        - `dashboard.py` - Primary automation control panel
        - `worker.py` - Background thread for browser operations
    - `profile/` - Profile management and data
    - `scraper/` - Job scraping and scoring
        - `jobspy_client.py` - Interface for job scraping
        - `scorer.py` - Job relevance scoring and filtering
- `assets/` - Static assets
- `tests/` - Test suite
