"""Loop detection for form processing flows."""

MAX_SAME_STATE_COUNT: int = 5
URL_SIMILARITY_THRESHOLD: float = 1.0
ELEMENT_COUNT_TOLERANCE: int = 5


class LoopDetector:
    """Detects when form processing is stuck in a loop."""

    def __init__(self) -> None:
        self._page_states: list[tuple[str, int, int, bool]] = []
        self._action_results: list[bool] = []

    def record_state(
        self,
        url: str,
        element_count: int,
        actions_executed: int = 0,
        actions_succeeded: bool = True,
    ) -> None:
        """Record current page state for loop detection."""
        self._page_states.append((url, element_count, actions_executed, actions_succeeded))

    def record_action_result(self, success: bool) -> None:
        """Track individual action outcomes."""
        self._action_results.append(success)

    def is_looping(self) -> bool:
        """Check if recent states indicate a loop condition."""
        if len(self._page_states) < MAX_SAME_STATE_COUNT:
            return False

        recent = self._page_states[-MAX_SAME_STATE_COUNT:]
        if not self._urls_same(recent):
            return False
        if not self._counts_similar(recent):
            return False
        return self._no_successful_actions(recent)

    def _urls_same(self, states: list[tuple[str, int, int, bool]]) -> bool:
        """Check if all URLs in states are identical."""
        return all(state[0] == states[0][0] for state in states)

    def _counts_similar(self, states: list[tuple[str, int, int, bool]]) -> bool:
        """Check if element counts are within tolerance."""
        return all(
            abs(state[1] - states[0][1]) <= ELEMENT_COUNT_TOLERANCE
            for state in states
        )

    def _no_successful_actions(self, states: list[tuple[str, int, int, bool]]) -> bool:
        """Check if recent states had no successful actions."""
        for _, _, actions_executed, actions_succeeded in states:
            if actions_executed > 0 and actions_succeeded:
                return False
        return True

    def reset(self) -> None:
        """Clear all recorded states."""
        self._page_states.clear()
        self._action_results.clear()
