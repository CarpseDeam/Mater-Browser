# Architecture

System architecture documentation.

## Form Processing

The `FormProcessor` handles the interaction with web forms. It includes logic to:
- Detect if a page is a job description vs. an actual application form.
- Automatically scroll to reveal "Apply" buttons if no form actions are initially detected.
- Fallback to regex-based button matching (e.g., "Apply") if structured analysis fails.

## Success Detection

The `SuccessDetector` component is responsible for determining if an application has been successfully submitted. It employs a multi-layered approach:
1. **URL Signal**: Matches current URL against known success patterns (e.g., `/thank-you`, `/confirmation`).
2. **Content Signal**: Scans page text for confirmation phrases (e.g., "application submitted").
3. **State Signal**: Detects when form elements disappear from the page, indicating a successful transition.
