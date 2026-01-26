# API Reference

API documentation.

## Agent API

### `FormProcessor`

Handles multi-page application flows.

- `process(job_url: str, source: Optional[JobSource] = None) -> ApplicationResult`: Orchestrates the form-filling process, including page classification, action execution, and scrolling fallbacks for job description pages.

### `SuccessDetector`

Dedicated success detection for application completion.

- `check() -> CompletionResult`: Evaluates all completion signals (URL, text, form state) and returns the first matching success indicator.
