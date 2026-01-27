# Changelog

All notable changes to this project.

- 2026-01-27: fix: Move and rename stuck detection files to correct locations
- 2026-01-27: feat: Implement FormProcessorStuckDetection to prevent infinite loops
  - Introduced `FormProcessorStuckDetection` to track page states and detect repetitions
  - Implemented content hashing to detect identical page states accurately
  - Added detection for repeating sequences of 2-3 pages (A-B-A-B or A-B-C-A-B-C)
  - Integrated with `FormProcessor` to automatically halt when stuck behavior is identified
- 2026-01-27: fix: Resolve GUI freezing by moving browser operations to background worker
  - Introduced `ApplyWorker` to handle all Playwright and automation tasks in a separate thread
  - Implemented thread-safe communication between GUI and background worker using queues and signals
  - Refactored `DashboardApp` to be fully responsive during job applications and scraping
- 2026-01-27: feat: Enhance Indeed Easy Apply deterministic filler
  - Integrated `IndeedFormFiller` into `ExternalFlow` for reliable, non-AI Indeed applications
  - Added `IndeedHelpers` for handling specific Indeed UI elements like resume cards and modals
  - Improved `IndeedFormFiller` selectors and added detection for resume selection pages
  - Added comprehensive state handling (resume, review, success) for Indeed's multi-step flow

- 2026-01-27: feat: Implement deterministic Indeed Easy Apply form filler       
  - Added `IndeedFormFiller` for config-driven, deterministic filling of Indeed application forms
  - Integrated with `AnswerEngine` for consistent answers across LinkedIn and Indeed
  - Implemented specific selectors for Indeed's unique DOM structure, including "rich-text-question-input"
  - Added comprehensive behavior tests in `tests/test_indeedformfiller.py`      

- 2026-01-26: feat: Implement deterministic LinkedIn Easy Apply form filler     
  - Introduced `AnswerEngine` for config-driven, fuzzy-matched question answering
  - Added `LinkedInFormFiller` to handle LinkedIn Easy Apply modals without LLM intervention
  - Created `config/answers.yaml` for storing deterministic personal and experience data
  - Updated `LinkedInFlow` to use the new deterministic filler, with Claude as a fallback
- 2026-01-26: refactor: Standardize ATS handlers and fix naming inconsistencies 
  - Standardized all ATS handlers to use `detect_page_state`, `FormPage`, and `PageResult` to match `BaseATSHandler`
  - Fixed inconsistencies in `LeverHandler`, `PhenomHandler`, and `IndeedHandler` where `PageState` and `HandlerResult` were incorrectly used
  - Renamed `detect_page_type` to `detect_page_state` in `SmartRecruitersHandler` and `ICIMSHandler` for consistency
  - Standardized documentation in `API.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, and `STRUCT.md` to reflect the new handler flow
- 2026-01-26: fix: Fix ATS enum mismatch by adding SMARTRECRUITERS and TALEO to ATSType
  - Added `SMARTRECRUITERS` and `TALEO` to `ATSType` enum in `src/ats/detector.py`
  - Updated `ATS_URL_PATTERNS` and `ATS_PAGE_SIGNATURES` with patterns for SmartRecruiters and Taleo
  - Standardized `ATSType` names (e.g., `INDEED_EASY` to `INDEED`)
  - Refactored `BaseATSHandler` to use `detect_page_state` and added `apply()` flow logic

- 2026-01-26: feat: Build ATS-first architecture with deterministic handlers    
  - Replaced "throw everything at Claude" approach with deterministic ATS-specific handlers for Workday, Greenhouse, Lever, iCIMS, and Phenom
  - Implemented `ATSDetector` to identify ATS systems from URL patterns and page signatures
  - Created `BaseATSHandler` and specific implementations for major ATS platforms to provide reliable, non-AI application filling
  - Added `FieldMapper` for consistent mapping of profile data to ATS-specific fields
  - Integrated ATS handlers into `FormProcessor`, with Claude remaining as a robust fallback for unknown systems

- 2026-01-26: fix: Strengthen form advancement logic in FormProcessor and prompts
  - Added `_ensure_plan_has_submit` failsafe to automatically append Next/Submit button clicks if missing from agent plan
  - Overhauled `SYSTEM_PROMPT` with mandatory rules for clicking advancement buttons even for pre-filled forms
  - Added "Common Mistakes" section to Claude prompts to prevent hangs on completed forms
  - Implemented prioritized keyword matching for locating the best submit button (Submit > Next > Continue > Review > Apply)

- 2026-01-26: feat: Rewrite Claude prompt for improved job application form filling
  - Implemented explicit page state detection (Job Listing, Application Form, Confirmation)
  - Added strict element filtering to ignore navigation/footer links and focus on form inputs
  - Defined form-filling priorities (Required fields > Contact info > Location > etc.)
  - Standardized field matching for common ATS questions (Work authorization, EEO, etc.)
  - Updated `build_form_prompt` to include `page_type` classification in the expected JSON output

- 2026-01-26: refactor: Simplify LinkedIn navigation logic and use centralized wait constants
  - Refactored `LinkedInFlow` to use `MAX_POPUP_WAIT_ATTEMPTS`, `MEDIUM_WAIT_MS`, and `LONG_WAIT_MS`
  - Simplified navigation in `LinkedInFlow.run` by leveraging the new `Page.goto` retry logic and removing redundant SPA-specific error handling

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