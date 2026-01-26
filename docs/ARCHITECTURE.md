# Architecture

System architecture documentation.

## Form Processing

The `FormProcessor` handles the interaction with web forms. When the analysis model returns no actionable elements, it delegates to `ZeroActionsHandler` to:
- **Classify Page State**: Distinguish between job descriptions, confirmation pages, loading states, and error pages.
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
- **React Select**: Specialized logic for interacting with complex React-based select components.

## Job Scoring & Filtering

The `JobScorer` filters and ranks job listings using a centralized `FilterConfig` system:
- **Centralized Configuration**: All rules (title/stack/role exclusions, keywords, blocked domains) and scoring weights are managed via `FilterConfig` (loaded from `config/filters.yaml`).
- **Granular Filtering**: Uses `FilterResult` to provide specific reasons for rejection, classified by `RuleType`.
- **Statistical Tracking**: Employs `FilterStats` to track rejection breakdowns across job batches.
- **Python-First Requirement**: Enforces that "Python" must appear in the job title or description based on configurable rules.
- **External ATS & Domain Blocking**: Automatically filters jobs from blocked domains or external ATS patterns that require account creation.
