# API Reference

API documentation.

## Agent API

### `PageClassifier`

Classifies job pages and finds primary action buttons.

- `classify() -> PageType`: Analyzes the current page to determine its type (e.g., `EASY_APPLY`, `EXTERNAL_LINK`, `ALREADY_APPLIED`).
- `find_apply_button(refresh: bool = False) -> Optional[ElementCandidate]`: Identifies the best candidate for an "Apply" button on the page using weighted scoring.
- `click_apply_button(candidate: ElementCandidate, timeout: int = 5000) -> bool`: Attempts to click the identified button using a robust multi-stage retry sequence.

### `AnswerEngine`

Config-driven answer lookup for form questions.

- `get_answer(question: str, field_type: str = "text") -> Optional[Any]`: Looks up an answer for a given question text by matching against `config/answers.yaml` patterns.
- `has_answer(question: str) -> bool`: Checks if an answer is available for the specified question.

### `LinkedInFormFiller`

Deterministic form filler for LinkedIn Easy Apply modals.

- `fill_current_modal() -> tuple[bool, list[str]]`: Fills all fields in the current modal. Returns success status and a list of any unknown questions.
- `click_next() -> bool`: Clicks the next, submit, or review button to advance the form.
- `is_confirmation_page() -> bool`: Detects if the application success page has been reached.
- `close_modal()`: Closes the Easy Apply modal after completion or failure.

### `FormProcessor`

Handles multi-page application flows.

- `process(job_url: str, source: Optional[JobSource] = None) -> ApplicationResult`: Orchestrates the form-filling process. It first attempts to use a deterministic `BaseATSHandler` (via `get_handler`). If no handler is available, it falls back to the Claude-based processing, including automated recovery via `ZeroActionsHandler`. Retrieves `ANTHROPIC_API_KEY` from environment for vision support.

## ATS API

### `ATSDetector`

Identifies ATS systems from URL patterns and page content.

- `detect() -> ATSType`: Analyzes the current page URL and DOM signatures to return the detected `ATSType` (e.g., `WORKDAY`, `GREENHOUSE`, `LEVER`).

### `get_handler`

- `get_handler(page: Page, profile: dict, resume_path: Optional[str] = None) -> Optional[BaseATSHandler]`: Factory function that returns the appropriate `BaseATSHandler` implementation if an ATS is detected and a handler exists.

### `BaseATSHandler`

Abstract base class for all ATS-specific handlers.

- `detect_page_state() -> FormPage`: Identifies the current application state (e.g., `FORM`, `REVIEW`, `CONFIRMATION`).
- `fill_current_page() -> PageResult`: Executes the logic to fill fields for the current page.
- `advance_page() -> PageResult`: Clicks next/submit to advance the form.
- `apply() -> PageResult`: Main entry point to run the full application flow.
### `ZeroActionsHandler`

Handles edge cases when no form actions are detected.

- `__init__(page: Page, api_key: Optional[str] = None)`: Initializes the handler with a Playwright page and optional API key for vision fallback.
- `classify_and_handle(input_count: int) -> Tuple[PageState, bool]`: Classifies the current page (e.g., JD, confirmation, loading) and attempts automated recovery (scrolling, clicking fallback buttons, vision-based detection).

### `VisionFallback`

Uses Claude vision to find elements when DOM detection fails.

- `find_and_click_apply() -> bool`: Takes a screenshot, identifies the "Apply" button using Claude, and performs a mouse click at the detected coordinates.

### `SuccessDetector`

Dedicated success detection for application completion.

- `check() -> CompletionResult`: Evaluates all completion signals (URL, text, form state) and returns the first matching success indicator.
- `mark_form_filled()`: Marks that a form has been interacted with, enabling the form-disappearance signal.
- `reset()`: Resets the detection state for a new application session.

### `Prompts`

Functions for generating LLM prompts.

- `build_form_prompt(dom_text: str, profile: dict) -> str`: Constructs a detailed user prompt containing the current page elements and the applicant's profile, instructing the agent to classify the page (returning a `page_type`) and plan actions.

## Data Models

### `ActionPlan`

The structured response from the Claude agent.

- `page_type: PageType`: Classification of the current page (`job_listing`, `form`, `confirmation`, or `unknown`).
- `reasoning: str`: Brief explanation of the agent's decision.
- `actions: list[Action]`: Ordered list of actions to execute.
- `needs_more_pages: bool`: Whether the agent expects more pages to follow.

### `PageType`

A literal string type for page classification:
- `job_listing`: A page showing job details with an "Apply" button.
- `form`: An application form with input fields.
- `confirmation`: A "Thank You" or "Application Submitted" page.
- `unknown`: State could not be determined.

## Scraper API

### `JobScorer`

Evaluates and filters job listings based on relevance using centralized configuration.

- `check_filter(job: JobListing) -> FilterResult`: Performs detailed evaluation of a job against all configured rules and returns a result containing pass/fail status and the specific reason.
- `score(job: JobListing) -> float`: Calculates the relevance score (0.0 to 1.0). Returns 0.0 if the job fails any filter.
- `explain(job: JobListing) -> str`: Generates a detailed text explanation of why a job passed or failed, including all matched exclusion rules and scoring breakdown.
- `filter_and_score(jobs: list[JobListing]) -> list[JobListing]`: Processes a batch of jobs, returning those that pass filtering, sorted by score. Logs a summary of filter statistics.
- `passes_filter(job: JobListing) -> bool`: Convenience method that returns `True` if the job listing meets all criteria.
