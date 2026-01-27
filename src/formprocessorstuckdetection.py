"""Stuck detection for form processor to prevent infinite loops."""
from dataclasses import dataclass, field
from typing import Optional
import hashlib


MAX_SAME_PAGE_ITERATIONS: int = 5
MAX_SAME_CONTENT_HASH_COUNT: int = 3
ELEMENT_COUNT_TOLERANCE: int = 5


@dataclass
class PageSnapshot:
    """Snapshot of page state for comparison."""
    url: str
    element_count: int
    content_hash: str
    actions_executed: int
    actions_succeeded: bool


@dataclass
class StuckResult:
    """Result of stuck detection check."""
    is_stuck: bool
    reason: Optional[str] = None
    iteration_count: int = 0


class FormProcessorStuckDetection:
    """Detects when form processing is stuck repeating the same page.

    Improves on basic loop detection by tracking:
    - Page content hashes to detect truly identical states
    - Iteration count on same URL regardless of action success
    - Pattern detection for repeating sequences
    """

    def __init__(
        self,
        max_same_page: int = MAX_SAME_PAGE_ITERATIONS,
        max_same_content: int = MAX_SAME_CONTENT_HASH_COUNT,
        element_tolerance: int = ELEMENT_COUNT_TOLERANCE,
    ) -> None:
        self._max_same_page = max_same_page
        self._max_same_content = max_same_content
        self._element_tolerance = element_tolerance
        self._snapshots: list[PageSnapshot] = []
        self._url_counts: dict[str, int] = {}
        self._content_hash_counts: dict[str, int] = {}

    def record_page(
        self,
        url: str,
        element_count: int,
        page_content: str,
        actions_executed: int = 0,
        actions_succeeded: bool = True,
    ) -> None:
        """Record a page visit for stuck detection.

        Args:
            url: Current page URL
            element_count: Number of interactive elements found
            page_content: Page HTML/text content for hashing
            actions_executed: Number of actions executed on this page
            actions_succeeded: Whether actions completed successfully
        """
        content_hash = self._compute_content_hash(page_content)
        snapshot = PageSnapshot(
            url=url,
            element_count=element_count,
            content_hash=content_hash,
            actions_executed=actions_executed,
            actions_succeeded=actions_succeeded,
        )
        self._snapshots.append(snapshot)

        normalized_url = self._normalize_url(url)
        self._url_counts[normalized_url] = self._url_counts.get(normalized_url, 0) + 1
        self._content_hash_counts[content_hash] = self._content_hash_counts.get(content_hash, 0) + 1

    def check_stuck(self) -> StuckResult:
        """Check if the form processor is stuck.

        Returns:
            StuckResult with is_stuck=True if stuck condition detected
        """
        if not self._snapshots:
            return StuckResult(is_stuck=False)

        same_content_result = self._check_same_content_hash()
        if same_content_result.is_stuck:
            return same_content_result

        same_page_result = self._check_same_page_iterations()
        if same_page_result.is_stuck:
            return same_page_result

        repeating_result = self._check_repeating_pattern()
        if repeating_result.is_stuck:
            return repeating_result

        return StuckResult(is_stuck=False)

    def _check_same_content_hash(self) -> StuckResult:
        """Check if same exact content has been seen too many times."""
        if len(self._snapshots) < self._max_same_content:
            return StuckResult(is_stuck=False)

        recent = self._snapshots[-self._max_same_content:]
        first_hash = recent[0].content_hash

        if all(s.content_hash == first_hash for s in recent):
            return StuckResult(
                is_stuck=True,
                reason=f"Identical page content {self._max_same_content} times consecutively",
                iteration_count=self._max_same_content,
            )
        return StuckResult(is_stuck=False)

    def _check_same_page_iterations(self) -> StuckResult:
        """Check if same URL visited too many times."""
        if len(self._snapshots) < self._max_same_page:
            return StuckResult(is_stuck=False)

        recent = self._snapshots[-self._max_same_page:]
        first_url = self._normalize_url(recent[0].url)

        if not all(self._normalize_url(s.url) == first_url for s in recent):
            return StuckResult(is_stuck=False)

        if not all(
            abs(s.element_count - recent[0].element_count) <= self._element_tolerance
            for s in recent
        ):
            return StuckResult(is_stuck=False)

        return StuckResult(
            is_stuck=True,
            reason=f"Same page visited {self._max_same_page} times with similar element count",
            iteration_count=self._max_same_page,
        )

    def _check_repeating_pattern(self) -> StuckResult:
        """Detect repeating sequences of 2-3 pages (A-B-A-B or A-B-C-A-B-C)."""
        if len(self._snapshots) < 6:
            return StuckResult(is_stuck=False)

        for pattern_length in [2, 3]:
            if self._has_repeating_pattern(pattern_length, repetitions=3):
                return StuckResult(
                    is_stuck=True,
                    reason=f"Detected repeating {pattern_length}-page pattern",
                    iteration_count=pattern_length * 3,
                )
        return StuckResult(is_stuck=False)

    def _has_repeating_pattern(self, pattern_length: int, repetitions: int) -> bool:
        """Check if recent snapshots contain a repeating pattern."""
        required_length = pattern_length * repetitions
        if len(self._snapshots) < required_length:
            return False

        recent = self._snapshots[-required_length:]
        pattern = [self._normalize_url(s.url) for s in recent[:pattern_length]]

        for i in range(repetitions):
            start = i * pattern_length
            segment = [self._normalize_url(s.url) for s in recent[start:start + pattern_length]]
            if segment != pattern:
                return False
        return True

    def _compute_content_hash(self, content: str) -> str:
        """Compute hash of page content for comparison."""
        normalized = content.strip().lower()
        return hashlib.md5(normalized.encode(), usedforsecurity=False).hexdigest()[:16]

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison (remove fragments, trailing slashes)."""
        url = url.split('#')[0]
        url = url.rstrip('/')
        return url

    def get_url_visit_count(self, url: str) -> int:
        """Get number of times a URL has been visited."""
        normalized = self._normalize_url(url)
        return self._url_counts.get(normalized, 0)

    def get_total_iterations(self) -> int:
        """Get total number of page iterations recorded."""
        return len(self._snapshots)

    def reset(self) -> None:
        """Clear all recorded state."""
        self._snapshots.clear()
        self._url_counts.clear()
        self._content_hash_counts.clear()
