# Architecture

System architecture documentation.

## Page Classification

The `PageClassifier` is responsible for identifying the current state of a job application page and locating the primary action buttons.
- **Classification Logic**: Uses a combination of URL patterns, page content (e.g., "already applied", "job closed"), and DOM element analysis.
- **Apply Button Detection**: Employs a Similo-style weighted scoring system to find the most likely "Apply" button. It distinguishes between:
    - **Easy Apply**: Internal application flows (e.g., LinkedIn Easy Apply, Indeed Smart Apply).
    - **External Link**: Buttons that lead away from the platform to a company-specific ATS, detected via ARIA labels, roles (`role="link"`), and text patterns (e.g., "Apply on company site"). Handling involves modularized redirection logic to capture both popup-based and same-tab navigations, with immediate transitions to captured URLs to avoid analysis timeouts.
- **Robust Interaction**: Implements a multi-stage click sequence (standard click, bounding box center click, JavaScript `el.click()`, and forced click) to handle obscured or non-standard button implementations, including automatic dismissal of overlays from platforms like LinkedIn and Dice.

## Form Processing

The `FormProcessor` handles the interaction with web forms. It utilizes a multi-stage prompting strategy defined in `prompts.py` to guide the LLM agent:
- **Page State Detection**: The agent first classifies the page as a `job_listing`, `form`, or `confirmation` page to determine the appropriate course of action.
- **Element Filtering**: Actively ignores non-functional elements like headers, footers, and social links to reduce noise and token usage.
- **Prioritized Filling**: Enforces a strict order of operations (e.g., required fields and contact info before optional fields) and ensures the primary action button is clicked last.
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
