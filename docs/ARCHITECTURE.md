# Architecture

System architecture documentation.

## Page Classification

The `PageClassifier` is responsible for identifying the current state of a job application page and locating the primary action buttons.
- **Classification Logic**: Uses a combination of URL patterns, page content (e.g., "already applied", "job closed"), and DOM element analysis.
- **Apply Button Detection**: Prioritizes direct selector matching for LinkedIn to ensure high reliability. If no direct match is found, it employs a Similo-style weighted scoring system to find the most likely "Apply" button. It distinguishes between:
    - **Easy Apply**: Internal application flows (specifically LinkedIn Easy Apply).
    - **External Link**: Buttons that lead away from the platform to a company-specific ATS. The system proactively detects "External-only" jobs and skips them early to prioritize Easy Apply flows.
- **Robust Interaction**: Implements a multi-stage click sequence (standard click, bounding box center click, JavaScript `el.click()`, and forced click) to handle obscured or non-standard button implementations, including automatic dismissal of overlays (with a 3-second timeout to prevent classification hangs).

## LinkedIn Easy Apply Strategy

The system is optimized exclusively for LinkedIn "Easy Apply" flows. External job applications or other platforms are automatically detected and skipped to ensure high reliability and deterministic behavior.

### Direct Application Flow (2026 Optimization)
To maximize speed and reliability, the application flow uses a direct-check strategy:
- **Instant Skip**: Bypasses full page classification for the primary flow. It waits for the `domcontentloaded` state and a 1s stabilization delay to ensure job details are accessible, then performs a multi-selector check for the Easy Apply button. If no button is found (using stable 2026 selectors and fallbacks), it instantly checks for "Already applied" or "Job closed" phrases and skips the job.
- **Failure Diagnostics**: If the "Easy Apply" button is missing and the job is not clearly "applied" or "closed," the system performs a diagnostic check:
    - **Authentication Check**: Verifies if the session was redirected to a login or checkpoint page, returning a `NEEDS_LOGIN` status if so.
    - **Visual Evidence**: Saves a full-page screenshot to `data/debug_screenshots/no_easy_apply_{job_id}.png` for manual inspection.
- **Click Blocker Dismissal**: Automatically removes non-modal overlays (chat bubbles, cookie banners, toasts) that could intercept the click before attempting to open the modal.
- **Modal Wait & Retry**: Implements a dedicated `_wait_for_modal` sequence with 2026-specific selectors and a one-time retry (using fallback button detection) if the initial click fails to open the modal.

## Form Processing

The `ApplicationAgent` orchestrates the interaction with web forms using a platform-specific deterministic filler:

1. **LinkedIn Easy Apply**: Uses `LinkedInFormFiller` and `AnswerEngine` for rapid, non-AI modal filling.

This strategy avoids LLM hallucinations, reduces token costs, and provides consistent results based on the user's `answers.yaml` configuration.

### Deterministic LinkedIn Flow

#### Resilience and Reliability Layer (2026)
To ensure high completion rates across diverse LinkedIn configurations, a robust reliability layer has been added:

- **Flow Timeout**: Implements a hard 120-second timeout for the entire Easy Apply process to prevent infinite hangs.
- **Page Error Handling**: Each page iteration in the modal-filling loop is wrapped in a try/except block. If more than 2 consecutive errors occur, the application is aborted.
- **Modal Fill Timeout**: Added a 30-second timeout to `fill_current_modal` to prevent stalling on complex forms.
- **Validation Error Recovery**: Automatically detects inline form validation errors and attempts to fix them using fallback answers (e.g., numeric "0" for salary/years, generic text for textareas) before retrying the next step.
- **Stuck Recovery Mechanism**: If the modal state (hash) remains unchanged for too long, the system performs a one-time recovery attempt (scroll content down, re-fill form, and click next) before aborting.
- **Resume Upload Handling**: Automatically selects existing resume cards if available or clicks "Choose Resume" buttons to ensure required documents are present without blocking the flow.
- **Typeahead/Autocomplete Support**: Detects and handles `combobox` and `typeahead` inputs by typing slowly and interacting with the suggestion list.
- **Clean State Management**: Proactively dismisses any existing modals or dialogs before starting a new application and handles the "Discard application?" confirmation when closing modals.
- **Randomized Delays**: Replaces fixed sleep times with randomized intervals between application cycles (3-8s) and loops (5-15s) to better simulate human behavior.
- **Cleanup**: Always executes `_close_modal` to return the browser to a clean state after success, failure, or timeout.

#### 2026 DOM Optimization
To increase reliability and speed for LinkedIn applications, the system uses optimized 2026 selectors:

- **Direct Button Selection**: Uses a prioritized fallback strategy for early detection, including stable IDs (`#jobs-apply-button-id`), data attributes (`[data-live-test-job-apply-button]`), semantic classes (`button.jobs-apply-button`), and ARIA labels. Each selector is checked with a dedicated timeout to balance speed and discovery.
- **Aria-Label Stability**: Prioritizes case-insensitive `aria-label*` partial matches for navigation buttons (Next, Review, Submit) to handle varied translations and obfuscated classes.
- **Progress Monitoring**: Uses the ARIA `progressbar` role and `aria-valuenow` state for precise modal state tracking.

- **Answer Engine**: Matches form questions (via labels, placeholders, or ARIA attributes) against a predefined configuration in `config/answers.yaml` using regex and fuzzy matching. Supports a wide range of categories including personal info, experience, EEO/demographics (gender, race, veteran status, disability), salary expectations, language proficiency, and work preferences. It includes specialized logic for matching experience-related questions, including multi-technology experience calculation and smart dropdown matching. Patterns are prioritized to ensure EEO/demographic questions match correctly before generic personal information patterns. When an unknown question is encountered, it is automatically logged to the `FailureLogger` with the associated job metadata and a page snapshot.

- **Form Filler**: Automatically identifies and fills text inputs, textareas, selects, radio buttons, and checkboxes in the LinkedIn modal using a multi-stage selector strategy.
    - **Multi-Modal Selectors**: Employs a robust search strategy across multiple modal selectors (`.jobs-easy-apply-modal`, `.artdeco-modal`, `[role="dialog"]`) to handle variations in LinkedIn's UI across different job listings.
    - **Selector Priority**: To handle obfuscated CSS classes, selectors are prioritized in this order: `aria-label` attributes (most stable), `role` attributes, `data-test*` attributes, semantic tags (e.g., `tag[type='...']`), and finally CSS classes as a last resort.
    - **Intelligent Skill Matching**: For "Select all that apply" checkbox groups, it matches available options against the user's documented skills in `answers.yaml` to provide accurate technical profiles.
    - **Smart Dropdowns**: Implements multi-stage matching for select options (exact, partial, and numeric range for years of experience) to ensure the best answer is selected even when phrasing differs.
    - **Automation**: Includes specialized handling for autocomplete location fields and automatically unchecks the "follow company" option to maintain user privacy.
    - **Robust Advancement**: Includes retry logic for the next/submit button with detailed logging of button text and interaction outcomes.

- **Fail-Safe**: To ensure applications never stall on required fields:
    - **Text/Textarea**: Uses generic fallback answers ("See resume" or referral text) if no answer is configured. For fields identified as numeric (e.g., salary, years, rate), it uses "0" as a fallback to satisfy validation requirements.  
    - **Radio Groups**: Uses intelligent defaults based on question content to ensure safe and accurate applications. It automatically defaults to "No" for sensitive topics (previous employment, conflict of interest, referrals, crypto, legal actions) and "Yes" for essential requirements (work authorization, background checks, consent). For unknown Yes/No questions, it defaults to "No" as a safer option before falling back to the first available choice for non-binary groups.  
    - **Select/Dropdowns**: If no matching option is found in the configuration, it selects the first non-placeholder option as a last resort.
    - **Checkboxes**: For single checkboxes, it checks the box by default unless it contains spam keywords. For multi-select skill groups, it checks the first relevant option if no skills match.
    - **Logging**: All unknown questions are still logged to the `FailureLogger` for future configuration updates.

## Failure Logging

To enable continuous improvement, the system includes a structured failure logging layer.
- **Failure Categorization**: Failures are classified into specific types such as `unknown_question`, `stuck_loop`, `validation_error`, `timeout`, and `crash`. 
- **Contextual Data**: Each failure captures relevant context, including the job URL, page snapshots, and specific details (e.g., the exact question text for `unknown_question`).
- **Persistence**: Failures are stored in a thread-safe JSONL format in the `data/` directory.

## Loop & Stuck Detection
The system prevents infinite loops in the `LinkedInFlow` using specialized modal hashing.

- **LinkedIn Modal Hashing**: Monitors the Easy Apply modal for state changes using a comprehensive hashing strategy. It incorporates the progress bar percentage, `aria-valuenow` state, form element counts (inputs, selects, textareas, fieldsets), and visible question labels. This multi-factor hash allows for precise detection of stuck states even when the UI slightly changes. If the state remains identical across multiple attempts (up to a tolerance of 3), the flow is halted to prevent infinite loops.

## Job Scoring & Filtering

The `JobScorer` filters and ranks job listings using a centralized `FilterConfig` system:
- **Centralized Configuration**: All rules (title/stack/role exclusions, keywords, blocked domains, location exclusions, blocked companies) and scoring weights are managed via `FilterConfig` (loaded from `config/filters.yaml`).
- **Granular Filtering**: Uses `FilterResult` to provide specific reasons for rejection, classified by `RuleType`.
- **Exclusion Rules**:
    - **TITLE_HARD_EXCLUSIONS**: Immediate filtering of non-relevant roles (Staff/Principal, Mobile, DevOps, etc.).
    - **LOCATION_EXCLUSION**: Rejects jobs based on geographic location patterns.
    - **BLOCKED_COMPANIES**: Explicitly excludes specified companies from the application queue.

## Platform Support

- **LinkedIn**: Fully supported for Easy Apply flows. Primary target for automated applications.
- **Other Platforms**: Automatically detected and skipped to maintain high success rates on the supported platform.

## Code Standards

To maintain a lean and predictable codebase, the system adheres to strict architectural constraints:
- **Function Size**: Max 25 lines per function to ensure single-responsibility and readability.
- **File Size**: New files are limited to 200 lines to prevent bloat and promote modularity.
- **Low Nesting**: A maximum of one level of nesting is permitted within functions.
- **Composition Over Inheritance**: Favors functional composition and simple data structures (dataclasses, dicts) over complex class hierarchies.
- **Minimal Abstraction**: Avoids ceremony (Factories, Managers) in favor of direct, predictable data flow.
