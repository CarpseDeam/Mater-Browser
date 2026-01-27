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
        - `stuck_detection.py` - Detects and prevents infinite loops in form processing
        - `actions.py` - Defines action models and the `ActionPlan` structure   
        - `answer_engine.py` - Config-driven answer lookup for questions        
        - `linkedin_form_filler.py` - Deterministic filler for LinkedIn Easy Apply
        - `indeed_form_filler.py` - Deterministic filler for Indeed Easy Apply  
        - `indeed_helpers.py` - Specialized helpers for Indeed-specific UI interactions
        - `prompts.py` - Manages system and user prompts for Claude agent       
        - `form_processor.py` - Orchestrates form filling and multi-page flows  
        - `zero_actions_handler.py` - Handles edge cases (JD pages, errors) using DOM analysis and vision fallback
        - `vision_fallback.py` - Uses Claude vision to find elements when DOM detection fails
        - `success_detector.py` - Detects application completion via URL, text, and form state
        - `page_classifier.py` - Classifies pages and finds primary action buttons
    - `ats/`
        - `detector.py` - Identifies ATS systems (Workday, Greenhouse, etc.) from URLs and DOM signatures
        - `base_handler.py` - Abstract base class for deterministic ATS interaction
        - `field_mapper.py` - Maps generic profile fields to ATS-specific field names
        - `registry.py` - Manages the mapping between detected ATS types and their handlers
        - `handlers/` - Implementation of specific handlers (Workday, Greenhouse, Lever, iCIMS, Phenom, SmartRecruiters, Taleo)
        - `fallback.py` - Logic for falling back to Claude when no deterministic handler is available
    - `executor/`
        - `runner.py` - Manages execution of application plans
    - `feedback/`
        - `failure_logger.py` - Captures and logs application failures for analysis
        - `failure_summarizer.py` - Groups and ranks failures for easier analysis and auto-fixing
    - `gui/`
        - `app.py` - Main GUI application setup
        - `dashboard.py` - Primary automation control panel
        - `worker.py` - Background thread for non-blocking browser operations   
    - `profile/` - Profile management and data
- `assets/` - Static assets
- files: 1844
- dirs: 426
- lines: 14830