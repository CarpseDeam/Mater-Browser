# API Reference

API documentation.

## Agent API

### `FormProcessor`

Handles multi-page application flows.

- `process(job_url: str, source: Optional[JobSource] = None) -> ApplicationResult`: Orchestrates the form-filling process, including page classification, action execution, and automated recovery via `ZeroActionsHandler`. Retrieves `ANTHROPIC_API_KEY` from environment for vision support.

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

## Scraper API

### `JobScorer`

Evaluates and filters job listings based on relevance.

- `passes_filter(job: JobListing) -> bool`: Returns `True` if the job listing meets all criteria, including title exclusions and technology stack requirements.
- `_check_exclusion(job: JobListing) -> Optional[str]`: Internal method that identifies the specific reason for a job's exclusion, if any.
