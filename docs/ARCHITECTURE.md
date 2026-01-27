# Architecture

System architecture documentation.

## Page Classification

The `PageClassifier` is responsible for identifying the current state of a job application page and locating the primary action buttons.
- **Classification Logic**: Uses a combination of URL patterns, page content (e.g., "already applied", "job closed"), and DOM element analysis.
- **Apply Button Detection**: Prioritizes direct selector matching for known platforms (e.g., LinkedIn) to ensure high reliability. If no direct match is found, it employs a Similo-style weighted scoring system to find the most likely "Apply" button. It distinguishes between:
    - **Easy Apply**: Internal application flows (e.g., LinkedIn Easy Apply, Indeed Smart Apply).
    - **External Link**: Buttons that lead away from the platform to a company-specific ATS, detected via ARIA labels, roles (`role="link"`), and text patterns (e.g., "Apply on company site"). The system proactively detects "External-only" jobs (e.g., Indeed's "Apply on company site" or LinkedIn's external links) and skips them early to prioritize Easy Apply flows. For legitimate external transitions, it involves modularized redirection logic to capture both popup-based and same-tab navigations, with immediate transitions to captured URLs to avoid analysis timeouts.
- **Robust Interaction**: Implements a multi-stage click sequence (standard click, bounding box center click, JavaScript `el.click()`, and forced click) to handle obscured or non-standard button implementations, including automatic dismissal of overlays from platforms like LinkedIn and Dice.

## Easy Apply Only Strategy

The system is optimized for LinkedIn and Indeed "Easy Apply" flows. External job applications that redirect to third-party ATS (Workday, Greenhouse, etc.) are automatically detected and skipped to ensure high reliability and deterministic behavior.

## Form Processing

The `ApplicationAgent` orchestrates the interaction with web forms using platform-specific deterministic fillers:

1. **LinkedIn Easy Apply**: Uses `LinkedInFormFiller` and `AnswerEngine` for rapid, non-AI modal filling.
2. **Indeed Easy Apply**: Uses `IndeedFormFiller` and `AnswerEngine` to handle Indeed's multi-step Smart Apply flow.

This strategy avoids LLM hallucinations, reduces token costs, and provides consistent results based on the user's `answers.yaml` configuration.

### Deterministic LinkedIn Flow
To increase reliability and speed for LinkedIn applications, the system bypasses AI for Easy Apply modals:

- **Direct Button Selection**: Uses optimized CSS selectors to immediately identify the "Easy Apply" button, bypassing generic DOM analysis for faster interaction.

- **Answer Engine**: Matches form questions (via labels, placeholders, or ARIA attributes) against a predefined configuration in `config/answers.yaml` using regex and fuzzy matching. Supports a wide range of categories including personal info, experience, EEO/demographics (gender, race, veteran status, disability), salary expectations, language proficiency, and work preferences. Patterns are prioritized to ensure EEO/demographic questions match correctly before generic personal information patterns (e.g., preventing disability questions from being mistaken for personal website fields). When an unknown question is encountered, it is automatically logged to the `FailureLogger` with the associated job metadata and a page snapshot.

- **Form Filler**: Automatically identifies and fills text inputs, selects, radio buttons, and checkboxes in the LinkedIn modal.

- **Fail-Safe**: If an unknown question is encountered for which no answer is configured, the system gracefully skips the job and logs the missing question for future configuration.



### Deterministic Indeed Flow

Similar to LinkedIn, the Indeed Easy Apply flow uses a deterministic approach:  

- **Selector Precision**: Uses researched REAL selectors from live Indeed DOM (as of Jan 2026) to identify form fields and navigation buttons, including support for "rich-text-question-input" areas.

- **State Management**: Detects review and confirmation pages to ensure the application is submitted correctly.

- **Answer Integration**: Leverages the same `AnswerEngine` used by LinkedIn for consistent profile information across platforms.
## Success Detection

The `SuccessDetector` component is responsible for determining if an application has been successfully submitted. It employs a multi-layered approach:
1. **URL Signal**: Matches current URL against known success patterns (e.g., `/thank-you`, `/confirmation`).
2. **Content Signal**: Scans page text for confirmation phrases (e.g., "application submitted").
3. **State Signal**: Detects when form elements disappear from the page, indicating a successful transition. Only active if a form has been previously filled during the session to avoid false positives.

## Failure Logging & Feedback

To enable continuous improvement and automated recovery, the system includes a structured failure logging and analysis layer.
- **Failure Categorization**: Failures are classified into specific types such as `unknown_question`, `stuck_loop`, `validation_error`, `timeout`, `crash`, and `react_select_fail`.
- **Contextual Data**: Each failure captures relevant context, including the job URL, page snapshots, and specific details (e.g., the exact question text for `unknown_question`).
- **Persistence**: Failures are stored in a thread-safe JSONL format in the `data/` directory.
- **Summarization & Analysis**: The `FailureSummarizer` groups similar failures (using fuzzy matching for questions) and ranks them by frequency. This allows developers to quickly identify the most impactful issues.
- **Fix Generation**: The `ConfigSuggester` translates failure summaries into actionable fix instructions. For `unknown_question` types, it automatically generates regex patterns and configuration keys. For other types, it identifies the target files and provides context for manual or semi-automated resolution.        

## Self-Healing Automation

The `AutoRepairer` component provides self-healing capabilities by automatically addressing recurring failures.
- **Thread Safety**: Uses a dedicated `threading.Lock` to ensure atomic operations on the failure counter and repair state, preventing race conditions in multi-threaded environments.
- **Threshold-Based Repair**: Triggers a repair cycle when the number of unaddressed failures reaches a configurable threshold (default: 5).
- **Automated Dispatch**: When triggered, it generates a failure summary and fix suggestions formatted as a detailed Markdown specification. This spec, along with the local `project_path`, is dispatched to a bridge server (default: `http://localhost:5001/dispatch`) which interfaces with Claude Code via a `content` payload.
- **Cooldown Mechanism**: Prevents redundant repair attempts by enforcing a cooldown period (default: 10 minutes) between dispatches.
- **Non-Blocking Execution**: Runs repairs asynchronously to ensure that the main automation loop continues uninterrupted.

## Loop & Stuck Detection
The system prevents infinite loops using `FormProcessorStuckDetection` (in `src/agent/stuck_detection.py`). It captures page content hashes and sequence patterns to detect and halt when stuck behavior is identified, logging the failure for analysis.

- **Content Hashing**: Uses MD5 hashes of page content to detect when the browser is stuck on the exact same state.
- **URL Tracking**: Monitors normalized URL visit counts and element counts to detect repetitions even if content slightly changes.
- **Pattern Detection**: Identifies repeating sequences of pages (e.g., A-B-A-B or A-B-C-A-B-C) to break out of circular navigation loops.

## Action Execution

Individual actions are executed via `ActionRunner`, which provides robustness for common web patterns:
- **Hidden Inputs**: Automatically handles hidden radio and checkbox inputs by attempting to click their associated `<label>` elements or using direct JavaScript execution.
- **Upload Action**: Automatically resolves `<label>` elements to their associated file `<input>` if the model targets the label instead of the input directly.
- **React Select**: Specialized logic for interacting with complex React-based select components.

## Job Scoring & Filtering

The `JobScorer` filters and ranks job listings using a centralized `FilterConfig` system:
- **Centralized Configuration**: All rules (title/stack/role exclusions, keywords, blocked domains) and scoring weights are managed via `FilterConfig` (loaded from `config/filters.yaml`).
- **Granular Filtering**: Uses `FilterResult` to provide specific reasons for rejection, classified by `RuleType`.
- **Statistical Tracking**: Employs `FilterStats` to track rejection breakdowns across job batches.
- **Python-First Requirement**: Enforces that "Python" must appear in the job title or description based on configurable rules.
- **External ATS & Domain Blocking**: Automatically filters jobs from blocked domains or external ATS patterns that require account creation.
