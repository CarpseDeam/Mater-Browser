# Mater-Browser

**Language:** python
**Stack:** Pydantic, Pytest

## Changelog

- **2026-01-26**: Improved external LinkedIn flow and upload action robustness
  - Updated `LinkedInFlow` for immediate popup handling to prevent timeouts
  - Enhanced `ActionRunner` to resolve file input labels to their associated inputs
  - Added Dice modal dismissal to `PageClassifier` overlay cleanup

- **2026-01-26**: Enhanced PageClassifier detection and click robustness

  - Refactored `PageClassifier` to improve `EXTERNAL_LINK` vs `EASY_APPLY` classification using ARIA labels and roles

  - Implemented generator-based click retry sequence for more reliable interactions with complex buttons

  - Cleaned up internal classification logic and constant formatting

- **2026-01-26**: Centralized filter configuration and enhanced JobScorer

  - Introduced `FilterConfig` for externalized filter rules and weights

  - Added `FilterStats` for detailed rejection breakdown and batch statistics

  - Updated `JobScorer` with `check_filter` and `explain` methods for better debuggability

- **2026-01-26**: Enhanced job scoring and filtering logic

  - Added strict title-based exclusions and refined role/stack filters in `JobScorer`

  - Required "Python" to be present in title or early description

- **2026-01-26**: Refactored zero-action handling in FormProcessor

  - `src/agent/zero_actions_handler.py` - New component to handle job descriptions, loading states, and error pages when no form actions are detected

  - `FormProcessor` now uses `ZeroActionsHandler` for automated recovery and state classification

- **2026-01-26**: Improved form completion detection and payment page filtering 

  - Updated `FormProcessor` with additional success URL signals

  - Refined `PageClassifier` to ignore safe job application domains during payment detection

- **2026-01-26**: Improved form processing with scrolling and fallback logic    

  - `src/agent/form_processor.py` - Added job description detection, automatic scrolling for "Apply" buttons, and regex-based fallback clicking

- **2026-01-25**: Implemented Similo-inspired PageClassifier for apply button detection

  - `src/agent/page_classifier.py` - New module with batch DOM extraction and weighted scoring

  - `PageType` enum - Classifies pages as EASY_APPLY, EXTERNAL_LINK, ALREADY_APPLIED, CLOSED, LOGIN_REQUIRED, or UNKNOWN

  - `ElementCandidate` dataclass - Stores candidate element attributes and score

  - `PageClassifier` class - Extracts candidates in single JS call, scores using Similo-style weights

  - Refactored `application.py` to use PageClassifier instead of sequential locator chains



## Structure



- `config/` - Configuration

- `docs/` - Documentation

- `scripts/` - Scripts

- `src/` - Source code

    - `agent/`
  
                  - `form_processor.py` - Orchestrates form filling and multi-page flows      
  
          
  
                  - `zero_actions_handler.py` - Handles edge cases (JD pages, errors) using DOM analysis and vision fallback
  
          
  
                  - `vision_fallback.py` - Uses Claude vision to find elements when DOM detection fails
  
          
  
                  - `success_detector.py` - Detects application completion via URL, text, and form state
  
          - `page_classifier.py` - Classifies pages and finds primary action buttons
    - `scraper/`

        - `scorer.py` - Evaluates job relevance using centralized `FilterConfig`

        - `filter_config.py` - Manages filter rules and configuration

- `assets/` - Static assets

- files: 1844
- dirs: 426
- lines: 14830
