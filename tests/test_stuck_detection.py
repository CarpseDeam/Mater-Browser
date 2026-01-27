"""Tests for FormProcessorStuckDetection."""
import pytest
from src.stuck_detection import (
    FormProcessorStuckDetection,
    PageSnapshot,
    StuckResult,
    MAX_SAME_PAGE_ITERATIONS,
    MAX_SAME_CONTENT_HASH_COUNT,
)


@pytest.fixture
def detector() -> FormProcessorStuckDetection:
    """Create a fresh detector instance."""
    return FormProcessorStuckDetection()


@pytest.fixture
def detector_low_threshold() -> FormProcessorStuckDetection:
    """Create detector with low thresholds for easier testing."""
    return FormProcessorStuckDetection(
        max_same_page=3,
        max_same_content=2,
        element_tolerance=3,
    )


class TestBasicRecording:
    """Tests for basic page recording functionality."""

    def test_record_page_increments_count(self, detector: FormProcessorStuckDetection) -> None:
        """Recording a page should increment the iteration count."""
        assert detector.get_total_iterations() == 0
        detector.record_page("https://example.com/form", 10, "<html>content</html>")
        assert detector.get_total_iterations() == 1

    def test_record_multiple_pages(self, detector: FormProcessorStuckDetection) -> None:
        """Multiple page recordings should all be tracked."""
        detector.record_page("https://example.com/page1", 10, "content1")
        detector.record_page("https://example.com/page2", 15, "content2")
        detector.record_page("https://example.com/page3", 20, "content3")
        assert detector.get_total_iterations() == 3

    def test_url_visit_count_tracking(self, detector: FormProcessorStuckDetection) -> None:
        """URL visit counts should be tracked correctly."""
        detector.record_page("https://example.com/form", 10, "content1")
        detector.record_page("https://example.com/form", 10, "content2")
        detector.record_page("https://example.com/other", 10, "content3")
        assert detector.get_url_visit_count("https://example.com/form") == 2
        assert detector.get_url_visit_count("https://example.com/other") == 1

    def test_url_normalization_removes_fragments(self, detector: FormProcessorStuckDetection) -> None:
        """URLs with fragments should be treated as same URL."""
        detector.record_page("https://example.com/form#section1", 10, "content1")
        detector.record_page("https://example.com/form#section2", 10, "content2")
        assert detector.get_url_visit_count("https://example.com/form") == 2

    def test_url_normalization_removes_trailing_slash(self, detector: FormProcessorStuckDetection) -> None:
        """URLs with/without trailing slash should be treated as same."""
        detector.record_page("https://example.com/form/", 10, "content1")
        detector.record_page("https://example.com/form", 10, "content2")
        assert detector.get_url_visit_count("https://example.com/form") == 2


class TestNotStuckConditions:
    """Tests for conditions where detection should NOT report stuck."""

    def test_no_recordings_not_stuck(self, detector: FormProcessorStuckDetection) -> None:
        """Empty detector should not report stuck."""
        result = detector.check_stuck()
        assert result.is_stuck is False
        assert result.reason is None

    def test_few_iterations_not_stuck(self, detector: FormProcessorStuckDetection) -> None:
        """Less than threshold iterations should not be stuck."""
        for i in range(MAX_SAME_PAGE_ITERATIONS - 1):
            detector.record_page("https://example.com/form", 10, f"different content {i}")
        result = detector.check_stuck()
        assert result.is_stuck is False

    def test_different_urls_not_stuck(self, detector: FormProcessorStuckDetection) -> None:
        """Different URLs should not trigger stuck detection."""
        for i in range(10):
            detector.record_page(f"https://example.com/page{i}", 10, f"content{i}")
        result = detector.check_stuck()
        assert result.is_stuck is False

    def test_changing_element_count_not_stuck(
        self, detector_low_threshold: FormProcessorStuckDetection
    ) -> None:
        """Significant element count changes should not be stuck."""
        detector_low_threshold.record_page("https://example.com/form", 10, "content1")
        detector_low_threshold.record_page("https://example.com/form", 25, "content2")
        detector_low_threshold.record_page("https://example.com/form", 40, "content3")
        result = detector_low_threshold.check_stuck()
        assert result.is_stuck is False

    def test_progressing_through_form_not_stuck(self, detector: FormProcessorStuckDetection) -> None:
        """Normal form progression should not be stuck."""
        pages = [
            ("https://example.com/step1", "Personal Info"),
            ("https://example.com/step2", "Work History"),
            ("https://example.com/step3", "Education"),
            ("https://example.com/step4", "Review"),
            ("https://example.com/confirmation", "Thank you"),
        ]
        for url, content in pages:
            detector.record_page(url, 15, content)
        result = detector.check_stuck()
        assert result.is_stuck is False


class TestSameContentHashDetection:
    """Tests for identical content hash detection."""

    def test_same_content_consecutively_is_stuck(
        self, detector_low_threshold: FormProcessorStuckDetection
    ) -> None:
        """Same exact content multiple times should be stuck."""
        same_content = "<html><body>Exact same page</body></html>"
        detector_low_threshold.record_page("https://example.com/form", 10, same_content)
        detector_low_threshold.record_page("https://example.com/form", 10, same_content)
        result = detector_low_threshold.check_stuck()
        assert result.is_stuck is True
        assert "Identical page content" in result.reason

    def test_content_hash_is_case_insensitive(
        self, detector_low_threshold: FormProcessorStuckDetection
    ) -> None:
        """Content hashing should be case insensitive."""
        detector_low_threshold.record_page("https://example.com/form", 10, "SAME CONTENT")
        detector_low_threshold.record_page("https://example.com/form", 10, "same content")
        result = detector_low_threshold.check_stuck()
        assert result.is_stuck is True

    def test_content_hash_ignores_whitespace(
        self, detector_low_threshold: FormProcessorStuckDetection
    ) -> None:
        """Content hashing should ignore leading/trailing whitespace."""
        detector_low_threshold.record_page("https://example.com/form", 10, "  content  ")
        detector_low_threshold.record_page("https://example.com/form", 10, "content")
        result = detector_low_threshold.check_stuck()
        assert result.is_stuck is True


class TestSamePageIterationDetection:
    """Tests for same page iteration detection."""

    def test_same_page_many_times_is_stuck(
        self, detector_low_threshold: FormProcessorStuckDetection
    ) -> None:
        """Same URL many times with similar elements is stuck."""
        for i in range(3):
            detector_low_threshold.record_page(
                "https://example.com/form", 10, f"content{i}"
            )
        result = detector_low_threshold.check_stuck()
        assert result.is_stuck is True
        assert "Same page visited" in result.reason

    def test_same_page_with_action_success_still_stuck(
        self, detector_low_threshold: FormProcessorStuckDetection
    ) -> None:
        """Even successful actions on same page should detect stuck."""
        for i in range(3):
            detector_low_threshold.record_page(
                "https://example.com/form",
                10,
                f"content{i}",
                actions_executed=5,
                actions_succeeded=True,
            )
        result = detector_low_threshold.check_stuck()
        assert result.is_stuck is True

    def test_element_count_within_tolerance_is_stuck(
        self, detector_low_threshold: FormProcessorStuckDetection
    ) -> None:
        """Element counts within tolerance should still be stuck."""
        detector_low_threshold.record_page("https://example.com/form", 10, "content1")
        detector_low_threshold.record_page("https://example.com/form", 12, "content2")
        detector_low_threshold.record_page("https://example.com/form", 11, "content3")
        result = detector_low_threshold.check_stuck()
        assert result.is_stuck is True


class TestRepeatingPatternDetection:
    """Tests for repeating page pattern detection."""

    def test_two_page_repeating_pattern_detected(
        self, detector: FormProcessorStuckDetection
    ) -> None:
        """A-B-A-B-A-B pattern should be detected as stuck."""
        for _ in range(3):
            detector.record_page("https://example.com/pageA", 10, f"contentA{_}")
            detector.record_page("https://example.com/pageB", 10, f"contentB{_}")
        result = detector.check_stuck()
        assert result.is_stuck is True
        assert "repeating" in result.reason.lower()
        assert "2-page" in result.reason

    def test_three_page_repeating_pattern_detected(
        self, detector: FormProcessorStuckDetection
    ) -> None:
        """A-B-C-A-B-C-A-B-C pattern should be detected as stuck."""
        for i in range(3):
            detector.record_page("https://example.com/pageA", 10, f"contentA{i}")
            detector.record_page("https://example.com/pageB", 10, f"contentB{i}")
            detector.record_page("https://example.com/pageC", 10, f"contentC{i}")
        result = detector.check_stuck()
        assert result.is_stuck is True
        assert "3-page" in result.reason

    def test_incomplete_pattern_not_detected(
        self, detector: FormProcessorStuckDetection
    ) -> None:
        """Incomplete patterns should not trigger stuck."""
        detector.record_page("https://example.com/pageA", 10, "contentA1")
        detector.record_page("https://example.com/pageB", 10, "contentB1")
        detector.record_page("https://example.com/pageA", 10, "contentA2")
        detector.record_page("https://example.com/pageB", 10, "contentB2")
        result = detector.check_stuck()
        assert result.is_stuck is False


class TestReset:
    """Tests for reset functionality."""

    def test_reset_clears_all_state(
        self, detector_low_threshold: FormProcessorStuckDetection
    ) -> None:
        """Reset should clear all recorded state."""
        for i in range(3):
            detector_low_threshold.record_page(
                "https://example.com/form", 10, "same content"
            )
        assert detector_low_threshold.check_stuck().is_stuck is True

        detector_low_threshold.reset()

        assert detector_low_threshold.get_total_iterations() == 0
        assert detector_low_threshold.get_url_visit_count("https://example.com/form") == 0
        assert detector_low_threshold.check_stuck().is_stuck is False

    def test_can_record_after_reset(
        self, detector_low_threshold: FormProcessorStuckDetection
    ) -> None:
        """Recording should work normally after reset."""
        detector_low_threshold.record_page("https://example.com/form", 10, "content")
        detector_low_threshold.reset()
        detector_low_threshold.record_page("https://example.com/new", 15, "new content")
        assert detector_low_threshold.get_total_iterations() == 1
        assert detector_low_threshold.get_url_visit_count("https://example.com/new") == 1


class TestStuckResultContract:
    """Tests for StuckResult dataclass contract."""

    def test_stuck_result_has_reason_when_stuck(
        self, detector_low_threshold: FormProcessorStuckDetection
    ) -> None:
        """StuckResult should have reason when stuck."""
        detector_low_threshold.record_page("https://example.com/form", 10, "same")
        detector_low_threshold.record_page("https://example.com/form", 10, "same")
        result = detector_low_threshold.check_stuck()
        assert result.is_stuck is True
        assert result.reason is not None
        assert len(result.reason) > 0

    def test_stuck_result_has_iteration_count(
        self, detector_low_threshold: FormProcessorStuckDetection
    ) -> None:
        """StuckResult should include iteration count when stuck."""
        detector_low_threshold.record_page("https://example.com/form", 10, "same")
        detector_low_threshold.record_page("https://example.com/form", 10, "same")
        result = detector_low_threshold.check_stuck()
        assert result.iteration_count > 0

    def test_not_stuck_result_defaults(self, detector: FormProcessorStuckDetection) -> None:
        """Not stuck result should have proper defaults."""
        result = detector.check_stuck()
        assert result.is_stuck is False
        assert result.reason is None
        assert result.iteration_count == 0


class TestConfigurableThresholds:
    """Tests for configurable threshold parameters."""

    def test_custom_max_same_page_threshold(self) -> None:
        """Custom max_same_page threshold should be respected."""
        detector = FormProcessorStuckDetection(max_same_page=2)
        detector.record_page("https://example.com/form", 10, "content1")
        detector.record_page("https://example.com/form", 10, "content2")
        result = detector.check_stuck()
        assert result.is_stuck is True

    def test_custom_max_same_content_threshold(self) -> None:
        """Custom max_same_content threshold should be respected."""
        detector = FormProcessorStuckDetection(max_same_content=4)
        same_content = "identical content"
        for _ in range(3):
            detector.record_page("https://example.com/form", 10, same_content)
        result = detector.check_stuck()
        assert result.is_stuck is False

        detector.record_page("https://example.com/form", 10, same_content)
        result = detector.check_stuck()
        assert result.is_stuck is True

    def test_custom_element_tolerance(self) -> None:
        """Custom element_tolerance should be respected."""
        detector = FormProcessorStuckDetection(max_same_page=2, element_tolerance=0)
        detector.record_page("https://example.com/form", 10, "content1")
        detector.record_page("https://example.com/form", 11, "content2")
        result = detector.check_stuck()
        assert result.is_stuck is False


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_content_handled(self, detector: FormProcessorStuckDetection) -> None:
        """Empty content should be handled without error."""
        detector.record_page("https://example.com/form", 0, "")
        result = detector.check_stuck()
        assert result.is_stuck is False

    def test_empty_url_handled(self, detector: FormProcessorStuckDetection) -> None:
        """Empty URL should be handled without error."""
        detector.record_page("", 10, "content")
        assert detector.get_url_visit_count("") == 1

    def test_zero_element_count(self, detector_low_threshold: FormProcessorStuckDetection) -> None:
        """Zero element count pages should still trigger detection."""
        for _ in range(3):
            detector_low_threshold.record_page("https://example.com/form", 0, f"content{_}")
        result = detector_low_threshold.check_stuck()
        assert result.is_stuck is True

    def test_very_large_element_count(self, detector: FormProcessorStuckDetection) -> None:
        """Very large element counts should work correctly."""
        detector.record_page("https://example.com/form", 999999, "content")
        assert detector.get_total_iterations() == 1

    def test_special_characters_in_url(self, detector: FormProcessorStuckDetection) -> None:
        """URLs with special characters should be handled."""
        url = "https://example.com/form?param=value&other=123"
        detector.record_page(url, 10, "content")
        assert detector.get_url_visit_count(url) == 1

    def test_unicode_content(self, detector_low_threshold: FormProcessorStuckDetection) -> None:
        """Unicode content should be hashed correctly."""
        unicode_content = "こんにちは世界 🌍"
        detector_low_threshold.record_page("https://example.com/form", 10, unicode_content)
        detector_low_threshold.record_page("https://example.com/form", 10, unicode_content)
        result = detector_low_threshold.check_stuck()
        assert result.is_stuck is True
