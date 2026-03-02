# API Reference

API documentation for the simplified LinkedIn-only Mater-Browser.

## Agent API

### `ApplicationAgent`

Orchestrates the job application flow for LinkedIn Easy Apply.

- `__init__(tab_manager: TabManager, max_pages: int = 15)`: Initializes the agent.
- `apply(job_url: str) -> ApplicationResult`: Routes to `LinkedInFlow` if the URL matches LinkedIn patterns.

### `LinkedInFlow`

- `__init__(page: Page, tabs: TabManager, max_pages: int)`: Initializes the LinkedIn-specific flow.
- `apply(job_url: str) -> ApplicationResult`: Executes the full Easy Apply flow for a single job. Includes a hard 120-second timeout and per-page error resilience.

### `AnswerEngine`

Config-driven answer lookup for form questions.

- `get_answer(question: str, field_type: str = "text") -> Optional[Any]`: Looks up an answer for a given question text by matching against `config/answers.yaml` patterns. Supports `text`, `radio`, `checkbox`, `textarea`, and `select` field types.
- `has_answer(question: str) -> bool`: Checks if an answer is available for the specified question.

### `LinkedInFormFiller`

Deterministic form filler for LinkedIn Easy Apply modals.

- `fill_current_modal() -> bool`: Fills all fields in the current modal (text inputs, selects, radios, checkboxes, and multi-select groups). Includes a 30-second timeout to prevent stalling on complex forms.
    - **Intelligent Skill Matching**: Automatically matches multi-select skill checkboxes against the user's documented technical profile.
    - **Smart Dropdowns**: Employs fuzzy and range-based matching for experience and preference dropdowns.
    - **Intelligent Radio Defaults**: Applies safe defaults for Yes/No questions based on context (e.g., "No" for conflicts of interest, "Yes" for work authorization) when no explicit answer is found.
    - **Fail-Safe**: Uses fallback answers for unknown text fields (including numeric "0" fallbacks) to ensure completion.
    - **Multi-Modal Support**: Employs a robust search strategy using multiple selectors (`.artdeco-modal`, `[role="dialog"]`) to find and fill the Easy Apply modal.
    - Returns `True` if modal was found and processed.
- `click_next() -> bool`: Clicks the next, submit, or review button to advance the form. Includes retry logic and detailed logging of button interactions.
- `is_confirmation_page() -> bool`: Detects if the application success page has been reached.
- `close_modal()`: Closes the Easy Apply modal after completion or failure.

## GUI API

### `ApplyWorker`

Background worker for thread-safe browser automation.

- `start()`: Initializes the background thread and establishes the browser connection.
- `stop()`: Gracefully shuts down the worker and disconnects from the browser.
- `submit_apply(request: ApplyRequest)`: Queues a new job application request for processing.

### `FailureLogger`

Captures unknown questions for future configuration.

- `log(failure: ApplicationFailure) -> None`: Appends a structured failure record to the JSONL log file.
- `read_all(include_addressed: bool = False) -> list[ApplicationFailure]`: Retrieves all logged failures.

## Data Models

### `ApplicationStatus`

- `SUCCESS`: Application successfully submitted.
- `FAILED`: Application failed due to unknown questions or other errors.
- `SKIPPED`: Job skipped because it was external-only or non-LinkedIn.
- `ERROR`: Unexpected system error.
- `NEEDS_LOGIN`: User authentication required.

### `ApplicationResult`

Result of a job application attempt.

- `status: ApplicationStatus`: The outcome of the application (Success, Failed, etc.).
- `message: str`: A descriptive message about the result.
- `pages_processed: int`: Total number of pages interacted with during the flow.
- `url: str`: The final URL or job URL associated with the application.

## Scraper API

### `JobScorer`

Evaluates and filters job listings based on relevance using centralized configuration.

- `check_filter(job: JobListing) -> FilterResult`: Performs detailed evaluation of a job against all configured rules (including title, role, stack, location, and company exclusions).
- `score(job: JobListing) -> float`: Calculates the relevance score (0.0 to 1.0). Returns 0.0 if the job fails any filter.

### `JobSpyClient`

Interface for job scraping.

- `scrape(queries: list[str], location: str) -> list[JobListing]`: Executes job searches (defaulting to LinkedIn) and returns a list of job listings.
