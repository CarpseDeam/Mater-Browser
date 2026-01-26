"""Loop detection for form processing flows."""

MAX_SAME_STATE_COUNT: int = 3
URL_SIMILARITY_THRESHOLD: float = 1.0
ELEMENT_COUNT_TOLERANCE: int = 5


class LoopDetector:
    """Detects when form processing is stuck in a loop."""

    def __init__(self) -> None:
        self._page_states: list[tuple[str, int]] = []

    def record_state(self, url: str, element_count: int) -> None:
        """Record current page state for loop detection."""
        self._page_states.append((url, element_count))

    def is_looping(self) -> bool:
        """Check if recent states indicate a loop condition."""
        if len(self._page_states) < MAX_SAME_STATE_COUNT:
            return False

        recent = self._page_states[-MAX_SAME_STATE_COUNT:]
        urls_same = all(state[0] == recent[0][0] for state in recent)
        counts_similar = all(
            abs(state[1] - recent[0][1]) <= ELEMENT_COUNT_TOLERANCE
            for state in recent
        )
        return urls_same and counts_similar

    def reset(self) -> None:
        """Clear all recorded states."""
        self._page_states.clear()
