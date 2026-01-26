# Architecture

System architecture documentation.

## Form Processing

The `FormProcessor` handles the interaction with web forms. When the analysis model returns no actionable elements, it delegates to `ZeroActionsHandler` to:
- **Classify Page State**: Distinguish between job descriptions, confirmation pages, loading states, and error pages.
- **Recover from JD Pages**: Automatically scroll and search for "Apply" buttons if on a job description.
- **Handle Loading**: Wait for network idle or timeouts when loading spinners are detected.
- **Fallback Action**: Attempt to find generic "Next" or "Continue" buttons via scrolling as a last resort.

## Success Detection

The `SuccessDetector` component is responsible for determining if an application has been successfully submitted. It employs a multi-layered approach:
1. **URL Signal**: Matches current URL against known success patterns (e.g., `/thank-you`, `/confirmation`).
2. **Content Signal**: Scans page text for confirmation phrases (e.g., "application submitted").
3. **State Signal**: Detects when form elements disappear from the page, indicating a successful transition.

## Job Scoring & Filtering

The `JobScorer` filters and ranks job listings to ensure only relevant Python-based roles are processed:
- **Hard Exclusions**: Immediately rejects jobs with non-relevant titles (e.g., Staff, Lead, Architect, DevOps, Mobile, QA).
- **Stack & Role Filtering**: Excludes roles focused on Java, Rust, Cloud Infrastructure, or IoT.
- **Python-First Requirement**: Enforces that "Python" must appear in the job title or within the first 500 characters of the description.
- **External ATS Detection**: Detects if a job requires an external account (e.g., Workday) and can filter accordingly.
