# API Reference

API documentation.

## Agent API

### `PageClassifier`

Classifies job pages and finds primary action buttons.

- `classify() -> PageType`: Analyzes the current page to determine its type (e.g., `EASY_APPLY`, `EXTERNAL_LINK`, `ALREADY_APPLIED`).
- `find_apply_button(refresh: bool = False) -> Optional[ElementCandidate]`: Identifies the best candidate for an "Apply" button on the page using weighted scoring.
- `click_apply_button(candidate: ElementCandidate, timeout: int = 5000) -> bool`: Attempts to click the identified button using a robust multi-stage retry sequence.

### `FormProcessor`

Handles multi-page application flows.

- `process(job_url: str, source: Optional[JobSource] = None) -> ApplicationResult`: Orchestrates the form-filling process, including page classification, action execution, and automated recovery via `ZeroActionsHandler`. Includes a failsafe to ensure forms always advance by auto-appending clicks to submit/next buttons if the AI plan is incomplete. Retrieves `ANTHROPIC_API_KEY` from environment for vision support.

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
