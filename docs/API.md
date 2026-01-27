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

- `get_answer(question: str, field_type: str = "text", *, job_url: str = "", job_title: str = "", company: str = "", page_snapshot: str | None = None) -> Optional[Any]`: Looks up an answer for a given question text by matching against `config/answers.yaml` patterns. Logs unknown questions to `FailureLogger`.
- `has_answer(question: str) -> bool`: Checks if an answer is available for the specified question.

### `LinkedInFormFiller`

Deterministic form filler for LinkedIn Easy Apply modals.

- `fill_current_modal() -> tuple[bool, list[str]]`: Fills all fields in the current modal. Returns success status and a list of any unknown questions.
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

### `FormProcessorStuckDetection`

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

### `FormProcessor`

Handles multi-page application flows.

- `__init__(page, dom_service, claude, runner, tabs, profile, resume_path, timeout_seconds, max_pages, job_url="", job_title="", company="")`: Initializes the processor with job metadata for rich failure logging.
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

Self-healing coordinator for automated failure resolution.

- `__init__(threshold: int = 5, cooldown_minutes: int = 10)`: Configures the repair trigger threshold and cooldown period.
- `record_failure(failure: ApplicationFailure) -> None`: Increments the failure count and checks if a repair should be initiated.
- `maybe_repair() -> bool`: Evaluates if the threshold and cooldown conditions are met, and if so, dispatches a repair request. Returns `True` if a repair was dispatched.
- `reset() -> None`: Resets the failure count, typically called after a successful repair dispatch or manual intervention.

### `Prompts`
Functions for generating LLM prompts.
- `build_form_prompt(dom_text: str, profile: dict) -> str`: Constructs a detailed user prompt containing the current page elements and the applicant's profile, instructing the agent to classify the page (returning a `page_type`) and plan actions.

## Data Models

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