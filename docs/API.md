# API Reference

API documentation.

## Agent API

### `FormProcessor`

Handles multi-page application flows.

- `process(job_url: str, source: Optional[JobSource] = None) -> ApplicationResult`: Orchestrates the form-filling process, including page classification, action execution, and automated recovery via `ZeroActionsHandler`.

### `ZeroActionsHandler`

Handles edge cases when no form actions are detected.

- `classify_and_handle(input_count: int) -> Tuple[PageState, bool]`: Classifies the current page (e.g., JD, confirmation, loading) and attempts automated recovery (scrolling, clicking fallback buttons).

### `SuccessDetector`

Dedicated success detection for application completion.

- `check() -> CompletionResult`: Evaluates all completion signals (URL, text, form state) and returns the first matching success indicator.
