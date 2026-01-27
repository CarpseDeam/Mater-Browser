"""Tests for P0 bug fixes in the self-healing feedback loop."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.feedback.failure_logger import ApplicationFailure
from src.feedback.failure_summarizer import FailureSummarizer
from src.feedback.auto_repairer import AutoRepairer
from src.feedback.config_suggester import FixSuggestion


@pytest.fixture
def failure_with_question_key() -> ApplicationFailure:
    return ApplicationFailure(
        timestamp=datetime.now().isoformat(),
        job_url="https://example.com/job/123",
        job_title="Software Engineer",
        company="Example Corp",
        failure_type="unknown_question",
        details={
            "question": "What is your salary expectation?",
            "field_type": "text",
        },
        addressed=False,
    )


class TestFailureSummarizerQuestionKey:
    def test_summarizer_extracts_question_from_details(
        self, failure_with_question_key: ApplicationFailure
    ) -> None:
        summarizer = FailureSummarizer([failure_with_question_key])
        grouped = summarizer.get_top_unknown_questions()

        assert len(grouped) == 1
        canonical, count, _ = grouped[0]
        assert canonical == "What is your salary expectation?"
        assert count == 1


class TestAutoRepairerSpecFormat:
    def test_dispatch_sends_spec_and_project_path(self, tmp_path: Path) -> None:
        repairer = AutoRepairer(threshold=1, cooldown_minutes=0)
        repairer._failure_logger._log_path = tmp_path / "failures.jsonl"

        failure = ApplicationFailure(
            timestamp="2024-01-01T12:00:00",
            job_url="https://example.com/job/123",
            job_title="Test",
            company="Test Corp",
            failure_type="unknown_question",
            details={"question": "Test question?"},
            addressed=False,
        )
        repairer.record_failure(failure)

        failures = [failure]
        suggestions = [
            FixSuggestion(
                target_file="test.py",
                fix_type="add_pattern",
                description="Test fix",
                suggested_content="# test",
                failure_count=1,
            )
        ]
        spec = MagicMock()
        spec.description = "Test repair"
        spec.suggestions = suggestions

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("src.feedback.auto_repairer.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = MagicMock(return_value=mock_response)
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_client

            repairer._dispatch_repair_sync(spec, failures)

            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert "spec" in payload
            assert "project_path" in payload
            assert "# Fix Suggestions" in payload["spec"]
            assert "description" not in payload
            assert "suggestions" not in payload


class TestLinkedInFlowExternalLinkOrder:
    def test_external_link_returns_skipped_without_clicking_apply(self) -> None:
        from src.agent.linkedin_flow import LinkedInFlow
        from src.agent.page_classifier import PageType

        mock_page = MagicMock()
        mock_page.goto.return_value = True
        mock_page.url = "https://linkedin.com/jobs/123"

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = PageType.EXTERNAL_LINK
        mock_classifier.click_apply_button = MagicMock()

        flow = LinkedInFlow(
            page=mock_page,
            tabs=MagicMock(),
            claude=MagicMock(),
            profile={},
            resume_path=None,
            timeout_seconds=60,
            max_pages=10,
        )

        with patch("src.agent.linkedin_flow.PageClassifier", return_value=mock_classifier):
            result = flow.apply("https://linkedin.com/jobs/123")

        assert result.status.value == "skipped"
        assert "External application" in result.message
        mock_classifier.click_apply_button.assert_not_called()
