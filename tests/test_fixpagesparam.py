"""Tests for pages_processed parameter fix in flow handlers."""
import pytest
from src.agent.models import ApplicationResult, ApplicationStatus


class TestApplicationResultPagesProcessed:
    """Tests verifying ApplicationResult uses pages_processed parameter."""

    def test_application_result_accepts_pages_processed(self) -> None:
        """ApplicationResult should accept pages_processed keyword argument."""
        result = ApplicationResult(
            status=ApplicationStatus.SUCCESS,
            message="Application submitted",
            pages_processed=5,
            url="https://example.com/job",
        )
        assert result.pages_processed == 5

    def test_application_result_pages_processed_default(self) -> None:
        """ApplicationResult should default pages_processed to 0."""
        result = ApplicationResult(
            status=ApplicationStatus.FAILED,
            message="Failed",
            url="https://example.com/job",
        )
        assert result.pages_processed == 0

    def test_application_result_rejects_pages_kwarg(self) -> None:
        """ApplicationResult should reject 'pages' keyword argument."""
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            ApplicationResult(
                status=ApplicationStatus.SUCCESS,
                message="Test",
                pages=5,  # type: ignore[call-arg]
                url="https://example.com",
            )
