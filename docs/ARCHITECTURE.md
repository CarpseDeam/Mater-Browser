# Architecture

System architecture documentation.

## Page Classification

The `PageClassifier` is responsible for identifying the current state of a job application page and locating the primary action buttons.
- **Classification Logic**: Uses a combination of URL patterns, page content (e.g., "already applied", "job closed"), and DOM element analysis.
- **Apply Button Detection**: Employs a Similo-style weighted scoring system to find the most likely "Apply" button. It distinguishes between:
    - **Easy Apply**: Internal application flows (e.g., LinkedIn Easy Apply, Indeed Smart Apply).
    - **External Link**: Buttons that lead away from the platform to a company-specific ATS, detected via ARIA labels, roles (`role="link"`), and text patterns (e.g., "Apply on company site"). Handling involves modularized redirection logic to capture both popup-based and same-tab navigations, with immediate transitions to captured URLs to avoid analysis timeouts.
- **Robust Interaction**: Implements a multi-stage click sequence (standard click, bounding box center click, JavaScript `el.click()`, and forced click) to handle obscured or non-standard button implementations, including automatic dismissal of overlays from platforms like LinkedIn and Dice.

## ATS-First Architecture

The system utilizes an ATS-first approach to handle job applications deterministically whenever possible. This replaces the reliance on AI for well-known Applicant Tracking Systems (ATS).
- **ATS Detection**: The `ATSDetector` identifies the ATS being used (e.g., Workday, Greenhouse, Lever, iCIMS, Phenom, SmartRecruiters, Taleo) by analyzing URL patterns and unique DOM signatures.
- **Deterministic Handlers**: Each supported ATS has a specialized handler (inheriting from `BaseATSHandler`) that provides a standardized interface for reliable form interaction.
    - `detect_page_state()`: Identifies the current step (e.g., Personal Info, Questions, Review).
    - `fill_current_page()`: Executes the filling logic for the current page state.
    - `advance_page()`: Handles the transition to the next page (clicking Next or Submit).
    - `apply()`: Orchestrates the full end-to-end application flow using these standardized methods.
- **Field Mapping**: The `FieldMapper` ensures that profile data is correctly mapped to the specific field names and IDs used by different ATS platforms.       
- **Hybrid Strategy**: The system first attempts to use a deterministic handler. If no handler is found for the detected ATS, or if the ATS is unknown, it falls back to the Claude-based agent.

## User Interface & Background Operations

To maintain high responsiveness, the system strictly separates GUI operations from browser automation.
- **Background Worker**: The `ApplyWorker` (in `src/gui/worker.py`) runs in a dedicated thread and owns the `BrowserConnection` and `ApplicationAgent`.
- **Asynchronous Communication**: The GUI communicates with the worker via thread-safe message queues and Python's `threading` signals. This prevents blocking the main event loop during long-running tasks like job scraping or multi-step application flows.
- **Thread Isolation**: Playwright objects are managed exclusively within the worker thread to comply with its single-threaded execution model.

## Form Processing

The `FormProcessor` orchestrates the interaction with web forms using a hybrid strategy:

1. **ATS Handler Attempt**: It first tries to identify the ATS and use a deterministic handler from the `src/ats/` module.

2. **Deterministic Platform Filling**: For LinkedIn and Indeed Easy Apply, the system uses platform-specific deterministic fillers (`LinkedInFormFiller`, `IndeedFormFiller`) and an `AnswerEngine` to avoid LLM hallucinations and latency. Indeed applications are handled via `ExternalFlow` when "Easy Apply" patterns are detected on Indeed domains.

3. **Claude Fallback**: If no deterministic handler or filler is applicable, it utilizes a multi-stage prompting strategy defined in `prompts.py` to guide the LLM agent.


### Deterministic LinkedIn Flow

To increase reliability and speed for LinkedIn applications, the system bypasses AI for Easy Apply modals:

- **Answer Engine**: Matches form questions (via labels, placeholders, or ARIA attributes) against a predefined configuration in `config/answers.yaml` using regex and fuzzy matching.

- **Form Filler**: Automatically identifies and fills text inputs, selects, radio buttons, and checkboxes in the LinkedIn modal.

- **Fail-Safe**: If an unknown question is encountered for which no answer is configured, the system gracefully skips the job and logs the missing question for future configuration.



### Deterministic Indeed Flow

Similar to LinkedIn, the Indeed Easy Apply flow uses a deterministic approach:  

- **Selector Precision**: Uses Indeed-specific selectors to identify form fields, including support for "rich-text-question-input" areas.

- **State Management**: Detects review and confirmation pages to ensure the application is submitted correctly.

- **Answer Integration**: Leverages the same `AnswerEngine` used by LinkedIn for consistent profile information across platforms.


- **Element Filtering**: Actively ignores non-functional elements like headers, footers, and social links to reduce noise and token usage.
- **Prioritized Filling**: Enforces a strict order of operations (e.g., required fields and contact info before optional fields) and ensures the primary action button is clicked last.
- **Form Advancement Failsafe**: Automatically detects if the agent's plan fails to include a terminal click action on a multi-page form and appends a click to the most likely 'Submit' or 'Next' button to prevent execution hangs.
- **Recovery from Edge Cases**: When the analysis model returns no actionable elements, it delegates to `ZeroActionsHandler` to:    - **Classify Page State**: Distinguish between job descriptions, confirmation pages, loading states, and error pages.
- **Recover from JD Pages**: Automatically scroll and search for "Apply" buttons if on a job description.
- **Vision Fallback**: Employs `VisionFallback` to use Claude's vision capabilities as a second layer of detection when traditional DOM-based element analysis fails.
- **Handle Loading**: Wait for network idle or timeouts when loading spinners are detected.
- **Fallback Action**: Attempt to find generic "Next" or "Continue" buttons via scrolling as a last resort.

## Success Detection

The `SuccessDetector` component is responsible for determining if an application has been successfully submitted. It employs a multi-layered approach:
1. **URL Signal**: Matches current URL against known success patterns (e.g., `/thank-you`, `/confirmation`).
2. **Content Signal**: Scans page text for confirmation phrases (e.g., "application submitted").
3. **State Signal**: Detects when form elements disappear from the page, indicating a successful transition. Only active if a form has been previously filled during the session to avoid false positives.

## Loop & Stuck Detection

The system prevents infinite loops in `FormProcessor` using `FormProcessorStuckDetection` (in `src/stuck_detection.py`):
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