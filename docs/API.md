# API Reference

API documentation.

## Agent API

### `ApplicationAgent`

Orchestrates the job application flow for LinkedIn and Indeed.

- `__init__(tab_manager: TabManager, max_pages: int = 15)`: Initializes the agent. No longer requires profile or Claude settings.
- `apply(job_url: str) -> ApplicationResult`: Routes to `LinkedInFlow` or `ExternalFlow` based on the URL.

### `LinkedInFlow`

- `__init__(page: Page, tabs: TabManager, max_pages: int)`: Initializes the LinkedIn-specific flow.

### `ExternalFlow`

- `__init__(page: Page, tabs: TabManager, max_pages: int)`: Initializes the external/Indeed-specific flow.

### `AnswerEngine`

Config-driven answer lookup for form questions.

- `get_answer(question: str, field_type: str = "text", *, job_url: str = "", job_title: str = "", company: str = "", page_snapshot: str | None = None) -> Optional[Any]`: Looks up an answer for a given question text by matching against `config/answers.yaml` patterns. Supports `text`, `radio`, and `select` field types. Logs unknown questions to `FailureLogger`.
- `has_answer(question: str) -> bool`: Checks if an answer is available for the specified question.

### `LinkedInFormFiller`

Deterministic form filler for LinkedIn Easy Apply modals.

- `fill_current_modal() -> bool`: Fills all fields in the current modal (text inputs, selects, radios, checkboxes, and multi-select groups). 
    - **Intelligent Skill Matching**: Automatically matches multi-select skill checkboxes against the user's documented technical profile.
    - **Smart Dropdowns**: Employs fuzzy and range-based matching for experience and preference dropdowns.
    - **Fail-Safe**: Uses fallback answers for unknown text fields (including numeric "0" fallbacks) and selects/radios to ensure completion. 
    - Returns `True` if modal was found and processed.
- `click_next() -> bool`: Clicks the next, submit, or review button to advance the form.
- `is_confirmation_page() -> bool`: Detects if the application success page has been reached.
- `close_modal()`: Closes the Easy Apply modal after completion or failure.

### `IndeedFormFiller`

Deterministic form filler for Indeed Easy Apply pages.

- `fill_current_page() -> tuple[bool, list[str]]`: Fills all fields on the current Indeed form page. Returns success status and a list of unknown questions.
- `click_continue() -> bool`: Clicks the "Continue" or "Submit" button to advance the form.
- `is_success_page() -> bool`: Detects if the application success/confirmation page has been reached.
- `is_review_page() -> bool`: Checks if the form is on a review step before final submission.
- `is_resume_page() -> bool`: Detects if the current page is for resume selection/upload.

### `FormProcessorStuckDetection` (Legacy)

Detects when form processing is stuck repeating the same page.

- `record_page(url, element_count, page_content, ...)`: Records a page visit state for analysis.
- `check_stuck() -> StuckResult`: Evaluates recorded history to determine if a stuck condition (identical content, same URL limit, or repeating pattern) is met.
- `reset()`: Clears all recorded state for a new session.

## GUI API

### `ApplyWorker`

Background worker for thread-safe browser automation.

- `start()`: Initializes the background thread and establishes the browser connection.
- `stop()`: Gracefully shuts down the worker and disconnects from the browser.
- `submit_apply(request: ApplyRequest)`: Queues a new job application request for processing.
- `on_status(status: WorkerStatus)`: Callback for worker state updates (Connecting, Ready, Error, etc.).
- `on_result(result: ApplyResult)`: Callback for reporting the outcome of an application attempt.

### `SuccessDetector`

Dedicated success detection for application completion.

- `check() -> CompletionResult`: Evaluates all completion signals (URL, text, form state) and returns the first matching success indicator.
- `mark_form_filled()`: Marks that a form has been interacted with, enabling the form-disappearance signal.
- `reset()`: Resets the detection state for a new application session.

### `FailureLogger`

Captures and manages application failures for analysis.

- `log(failure: ApplicationFailure) -> None`: Appends a structured failure record to the JSONL log file.
- `read_all(include_addressed: bool = False) -> list[ApplicationFailure]`: Retrieves all logged failures, with an option to filter for unaddressed ones.
- `mark_addressed(timestamps: list[str]) -> None`: Marks specific failures as addressed based on their unique ISO timestamps.

### `FailureSummarizer`

Groups and ranks failures from the failure log for analysis.

- `__init__(failures: list[ApplicationFailure])`: Initializes with a list of failures to analyze.
- `summarize() -> list[FailureSummary]`: Groups failures by type and ranks them by frequency, returning top summaries.
- `get_top_unknown_questions(n: int = 10) -> list[tuple[str, int, list[str]]]`: Returns fuzzy-grouped unknown questions with their counts and similar variants.

### `ConfigSuggester`

Generates structured fix instructions from failure summaries.

- `suggest(summaries: list[FailureSummary]) -> list[FixSuggestion]`: Analyzes failure summaries and generates targeted fix suggestions, including regex patterns for new questions and selectors for React components.

### `AutoRepairer`

Self-healing coordinator for automated failure resolution. Thread-safe implementation.

- `__init__(threshold: int = 5, cooldown_minutes: int = 10)`: Configures the repair trigger threshold and cooldown period.
- `record_failure(failure: ApplicationFailure) -> None`: Increments the failure count (thread-safe) and checks if a repair should be initiated.
- `maybe_repair() -> bool`: Evaluates if the threshold and cooldown conditions are met (thread-safe), and if so, dispatches a repair request. Returns `True` if a repair was dispatched.
- `reset() -> None`: Resets the failure count (thread-safe), typically called after a successful repair dispatch or manual intervention.

## Data Models

### `ApplicationStatus`

- `SUCCESS`: Application successfully submitted.
- `FAILED`: Application failed due to unknown questions or other errors.
- `SKIPPED`: Job skipped because it was external-only or non-Easy Apply.
- `ERROR`: Unexpected system error.
- `NEEDS_LOGIN`: User authentication required.

### `ApplicationFailure`

Represents a structured application failure event.

- `timestamp: str`: ISO format timestamp of the failure.
- `job_url: str`: URL of the job application where the failure occurred.
- `job_title: str`: Title of the job.
- `company: str`: Name of the company.
- `failure_type: Literal[...]`: One of `unknown_question`, `stuck_loop`, `validation_error`, `timeout`, `crash`, `react_select_fail`.
- `details: dict`: Context-specific details varying by `failure_type`.
- `page_snapshot: Optional[str]`: Optional HTML or text snapshot of the page at the time of failure.
- `addressed: bool`: Whether this failure has been reviewed and resolved.

### `ApplicationResult`

Result of a job application attempt.

- `status: ApplicationStatus`: The outcome of the application (Success, Failed, etc.).
- `message: str`: A descriptive message about the result.
- `pages_processed: int`: Total number of pages interacted with during the flow.
- `url: str`: The final URL or job URL associated with the application.

### `FailureSummary`

Groups application failures by type and similarity.

- `failure_type: str`: The type of failure being summarized.
- `count: int`: Number of occurrences.
- `examples: list[ApplicationFailure]`: Up to 3 example failures for context.
- `grouped_questions: list[tuple[str, int, list[str]]]`: (For `unknown_question` type) Fuzzy-grouped question text and metadata.

### `FixSuggestion`

Represents a structured instruction for fixing an application failure.

- `target_file: str`: The source file that needs to be modified.
- `fix_type: Literal["add_pattern", "add_handler", "investigate", "no_action"]`: The strategy for the fix.
- `description: str`: Human-readable description of the issue and suggested fix.
- `suggested_content: str`: The specific code or configuration pattern suggested.
- `failure_count: int`: Number of failures this fix would address.

## Scraper API

### `JobScorer`

Evaluates and filters job listings based on relevance using centralized configuration.

- `check_filter(job: JobListing) -> FilterResult`: Performs detailed evaluation of a job against all configured rules (including title, role, stack, and geographic location exclusions) and returns a result containing pass/fail status and the specific reason.
- `score(job: JobListing) -> float`: Calculates the relevance score (0.0 to 1.0). Returns 0.0 if the job fails any filter.
- `explain(job: JobListing) -> str`: Generates a detailed text explanation of why a job passed or failed, including all matched exclusion rules and scoring breakdown.
- `filter_and_score(jobs: list[JobListing]) -> list[JobListing]`: Processes a batch of jobs, returning those that pass filtering, sorted by score. Logs a summary of filter statistics.
- `passes_filter(job: JobListing) -> bool`: Convenience method that returns `True` if the job listing meets all criteria.

### `JobSpyClient`

Interface for job scraping using the JobSpy library.

- `__init__(sites: list[str] = None, results_wanted: int = 20, hours_old: int = 72, country: str = "USA")`: Initializes the scraper. `sites` defaults to `["linkedin"]` (Indeed is disabled by default due to SmartApply unreliability).
- `scrape(queries: list[str], location: str) -> list[JobListing]`: Executes job searches across configured sites and returns a list of job listings.