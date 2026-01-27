from __future__ import annotations

import pytest

from src.feedback.config_suggester import ConfigSuggester, FixSuggestion
from src.feedback.failure_logger import ApplicationFailure
from src.feedback.failure_summarizer import FailureSummary


@pytest.fixture
def suggester() -> ConfigSuggester:
    return ConfigSuggester()


@pytest.fixture
def sample_failure() -> ApplicationFailure:
    return ApplicationFailure(
        timestamp="2024-01-01T00:00:00",
        job_url="https://example.com/job/1",
        job_title="Software Engineer",
        company="Example Corp",
        failure_type="unknown_question",
        details={"question_text": "What is your salary expectation?"},
    )


class TestUnknownQuestionMapping:
    def test_generates_add_pattern_fix_type(
        self, suggester: ConfigSuggester, sample_failure: ApplicationFailure
    ) -> None:
        summary = FailureSummary(
            failure_type="unknown_question",
            count=5,
            examples=[sample_failure],
            grouped_questions=[("What is your salary expectation?", 5, [])],
        )

        result = suggester.suggest([summary])

        assert len(result) == 1
        assert result[0].fix_type == "add_pattern"
        assert result[0].target_file == "src/agent/answer_engine.py"

    def test_generates_regex_pattern_in_suggested_content(
        self, suggester: ConfigSuggester, sample_failure: ApplicationFailure
    ) -> None:
        summary = FailureSummary(
            failure_type="unknown_question",
            count=3,
            examples=[sample_failure],
            grouped_questions=[("What is your salary expectation?", 3, [])],
        )

        result = suggester.suggest([summary])

        assert "QUESTION_PATTERNS" in result[0].suggested_content
        assert "config_key_1" in result[0].suggested_content


class TestReactSelectMapping:
    def test_generates_add_handler_fix_type(
        self, suggester: ConfigSuggester
    ) -> None:
        failure = ApplicationFailure(
            timestamp="2024-01-01T00:00:00",
            job_url="https://example.com/job/1",
            job_title="Software Engineer",
            company="Example Corp",
            failure_type="react_select_fail",
            details={"selector": ".react-select-container"},
        )
        summary = FailureSummary(
            failure_type="react_select_fail",
            count=3,
            examples=[failure],
        )

        result = suggester.suggest([summary])

        assert len(result) == 1
        assert result[0].fix_type == "add_handler"
        assert result[0].target_file == "src/agent/form_processor.py"
        assert ".react-select-container" in result[0].suggested_content


class TestValidationErrorMapping:
    def test_generates_investigate_fix_type(
        self, suggester: ConfigSuggester
    ) -> None:
        failure = ApplicationFailure(
            timestamp="2024-01-01T00:00:00",
            job_url="https://example.com/job/1",
            job_title="Software Engineer",
            company="Example Corp",
            failure_type="validation_error",
            details={
                "field_selector": "#email-input",
                "error_message": "Invalid email format",
            },
        )
        summary = FailureSummary(
            failure_type="validation_error",
            count=2,
            examples=[failure],
        )

        result = suggester.suggest([summary])

        assert len(result) == 1
        assert result[0].fix_type == "investigate"
        assert result[0].target_file == "src/agent/form_processor.py"
        assert "#email-input" in result[0].suggested_content
        assert "Invalid email format" in result[0].suggested_content


class TestStuckLoopMapping:
    def test_returns_no_suggestion(self, suggester: ConfigSuggester) -> None:
        failure = ApplicationFailure(
            timestamp="2024-01-01T00:00:00",
            job_url="https://example.com/job/1",
            job_title="Software Engineer",
            company="Example Corp",
            failure_type="stuck_loop",
            details={},
        )
        summary = FailureSummary(
            failure_type="stuck_loop",
            count=5,
            examples=[failure],
        )

        result = suggester.suggest([summary])

        assert len(result) == 0


class TestTimeoutMapping:
    def test_generates_investigate_fix_type(
        self, suggester: ConfigSuggester
    ) -> None:
        failure = ApplicationFailure(
            timestamp="2024-01-01T00:00:00",
            job_url="https://example.com/job/1",
            job_title="Software Engineer",
            company="Example Corp",
            failure_type="timeout",
            details={
                "page_url": "https://example.com/apply",
                "last_action": "click_submit",
            },
        )
        summary = FailureSummary(
            failure_type="timeout",
            count=2,
            examples=[failure],
        )

        result = suggester.suggest([summary])

        assert len(result) == 1
        assert result[0].fix_type == "investigate"
        assert "https://example.com/apply" in result[0].suggested_content
        assert "click_submit" in result[0].suggested_content


class TestCrashMapping:
    def test_generates_investigate_fix_type(
        self, suggester: ConfigSuggester
    ) -> None:
        failure = ApplicationFailure(
            timestamp="2024-01-01T00:00:00",
            job_url="https://example.com/job/1",
            job_title="Software Engineer",
            company="Example Corp",
            failure_type="crash",
            details={
                "exception_type": "ValueError",
                "exception_message": "Invalid input",
            },
        )
        summary = FailureSummary(
            failure_type="crash",
            count=1,
            examples=[failure],
        )

        result = suggester.suggest([summary])

        assert len(result) == 1
        assert result[0].fix_type == "investigate"
        assert "ValueError" in result[0].suggested_content
        assert "Invalid input" in result[0].suggested_content


class TestRegexPatternGeneration:
    def test_escapes_special_characters(
        self, suggester: ConfigSuggester, sample_failure: ApplicationFailure
    ) -> None:
        summary = FailureSummary(
            failure_type="unknown_question",
            count=1,
            examples=[sample_failure],
            grouped_questions=[("What is your salary (USD)?", 1, [])],
        )

        result = suggester.suggest([summary])

        assert r"\(USD\)" in result[0].suggested_content

    def test_replaces_numbers_with_digit_pattern(
        self, suggester: ConfigSuggester, sample_failure: ApplicationFailure
    ) -> None:
        summary = FailureSummary(
            failure_type="unknown_question",
            count=1,
            examples=[sample_failure],
            grouped_questions=[("Question 123 about experience", 1, [])],
        )

        result = suggester.suggest([summary])

        assert r"\d+" in result[0].suggested_content


class TestSortByFailureCount:
    def test_suggestions_sorted_descending_by_count(
        self, suggester: ConfigSuggester
    ) -> None:
        low_count = FailureSummary(
            failure_type="timeout",
            count=2,
            examples=[
                ApplicationFailure(
                    timestamp="2024-01-01T00:00:00",
                    job_url="https://example.com/job/1",
                    job_title="Engineer",
                    company="Corp",
                    failure_type="timeout",
                    details={},
                )
            ],
        )
        high_count = FailureSummary(
            failure_type="crash",
            count=10,
            examples=[
                ApplicationFailure(
                    timestamp="2024-01-01T00:00:00",
                    job_url="https://example.com/job/1",
                    job_title="Engineer",
                    company="Corp",
                    failure_type="crash",
                    details={},
                )
            ],
        )

        result = suggester.suggest([low_count, high_count])

        assert result[0].failure_count == 10
        assert result[1].failure_count == 2


class TestExampleDetailsIncluded:
    def test_includes_example_context(
        self, suggester: ConfigSuggester, sample_failure: ApplicationFailure
    ) -> None:
        summary = FailureSummary(
            failure_type="unknown_question",
            count=1,
            examples=[sample_failure],
            grouped_questions=[("What is your salary expectation?", 1, [])],
        )

        result = suggester.suggest([summary])

        assert "Example:" in result[0].suggested_content


class TestEdgeCases:
    def test_empty_summaries_returns_empty_list(
        self, suggester: ConfigSuggester
    ) -> None:
        result = suggester.suggest([])

        assert result == []

    def test_summary_with_zero_count_skipped(
        self, suggester: ConfigSuggester
    ) -> None:
        summary = FailureSummary(
            failure_type="crash",
            count=0,
            examples=[],
        )

        result = suggester.suggest([summary])

        assert result == []

    def test_stuck_loop_returns_empty_suggestion(
        self, suggester: ConfigSuggester
    ) -> None:
        summary = FailureSummary(
            failure_type="stuck_loop",
            count=10,
            examples=[
                ApplicationFailure(
                    timestamp="2024-01-01T00:00:00",
                    job_url="https://example.com/job/1",
                    job_title="Engineer",
                    company="Corp",
                    failure_type="stuck_loop",
                    details={},
                )
            ],
        )

        result = suggester.suggest([summary])

        assert len(result) == 0
