# Project Structure

**Language:** Python
**Stack:** Playwright, Pydantic, Pytest

## Directory Overview

- `config/` - Configuration files (`answers.yaml`, `filters.yaml`, `settings.yaml`)
- `data/` - Local data storage, logs, and DOM dumps
- `docs/` - System documentation
- `scripts/` - Utility scripts and batch files
- `src/` - Core source code
    - `agent/` - LinkedIn Easy Apply automation logic
        - `application.py` - Core application agent orchestrator
        - `linkedin_flow.py` - Orchestrates LinkedIn Easy Apply with resilience and timeouts
        - `linkedin_form_filler.py` - Deterministic filler for LinkedIn modals
        - `answer_engine.py` - Config-driven answer lookup with regex matching
        - `page_classifier.py` - Identifies page state and primary action buttons
        - `success_detector.py` - Verifies application submission
        - `models.py` - Shared data models, enums, and constants
        - `dom_extractor.py` - Utilities for extracting DOM state
        - `payment_blocker.py` - Safety checks to prevent accidental payments
        - `visibility_helpers.py` - Reliable element interaction checks
    - `automation/` - High-level automation runners
        - `runner.py` - Orchestrates scraping and applying cycles
        - `search_generator.py` - Generates targeted search queries
    - `browser/` - Playwright abstraction layer
        - `connection.py` - Browser lifecycle and connection management
        - `page.py` - Enhanced page interaction with retries
        - `tabs.py` - Manager for browser tabs and popup capturing
    - `core/` - Foundation modules
        - `config.py` - Centralized configuration loading (Pydantic)
        - `logging.py` - Structured logging configuration
    - `feedback/` - System improvement and failure logging
        - `failure_logger.py` - Records unknown questions and automation failures
    - `gui/` - Desktop interface
        - `app.py` - Main application entry point
        - `dashboard.py` - Primary control panel
        - `worker.py` - Background thread for browser automation
    - `profile/` - User profile management
    - `queue/` - Job application queue management
    - `scraper/` - Job discovery and evaluation
        - `filter_config.py` - Unified filtering and scoring rules
        - `jobspy_client.py` - Job search client (LinkedIn focused)
        - `scorer.py` - Heuristic job evaluation and filtering
- `tests/` - Comprehensive test suite
- `assets/` - Static resources and icons
- `run.py` - CLI entry point for the automation runner
- `gui.py` - Entry point for the graphical interface
