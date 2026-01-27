from __future__ import annotations

import pytest

from src.feedback.failure_logger import ApplicationFailure
from src.feedback.failure_summarizer import FailureSummarizer, FailureSummary


@pytest.fixture
def make_failure() -> callable:
    def _make(
        failure_type: str = "unknown_question",
        question_text: str | None = None,
        details: dict | None = None,
    ) -> ApplicationFailure:
        if details is None:
            details = {}
        if question_text is not None:
            details["question_text"] = question_text
        return ApplicationFailure(
            timestamp="2024-01-01T00:00:00",
            job_url="https://example.com/job",
            job_title="Software Engineer",
            company="Example Corp",
            failure_type=failure_type,
            details=details,
        )

    return _make


class TestFailureSummarizerGroupByType:
    def test_groups_failures_by_failure_type(
        self, make_failure: callable
    ) -> None:
        failures = [
            make_failure(failure_type="unknown_question"),
            make_failure(failure_type="timeout"),
            make_failure(failure_type="unknown_question"),
            make_failure(failure_type="crash"),
        ]
        summarizer = FailureSummarizer(failures)
        summaries = summarizer.summarize()

        types = {s.failure_type for s in summaries}
        assert types == {"unknown_question", "timeout", "crash"}

        unknown_summary = next(
            s for s in summaries if s.failure_type == "unknown_question"
        )
        assert unknown_summary.count == 2


class TestFailureSummarizerFuzzyGrouping:
    def test_fuzzy_groups_similar_questions(self, make_failure: callable) -> None:
        failures = [
            make_failure(question_text="Years of Python experience?"),
            make_failure(question_text="Years of Python experience"),
            make_failure(question_text="What is your favorite programming language?"),
        ]
        summarizer = FailureSummarizer(failures)
        groups = summarizer.get_top_unknown_questions()

        assert len(groups) == 2
        python_group = next(g for g in groups if "Python" in g[0])
        assert python_group[1] == 2

    def test_picks_shortest_question_as_canonical(
        self, make_failure: callable
    ) -> None:
        failures = [
            make_failure(question_text="What is your email address?"),
            make_failure(question_text="Your email address?"),
            make_failure(question_text="What is your email address"),
        ]
        summarizer = FailureSummarizer(failures)
        groups = summarizer.get_top_unknown_questions()

        top_group = groups[0]
        canonical = top_group[0]
        assert canonical == "Your email address?"


class TestFailureSummarizerSorting:
    def test_sorts_summaries_by_count_descending(
        self, make_failure: callable
    ) -> None:
        failures = [
            make_failure(failure_type="timeout"),
            make_failure(failure_type="crash"),
            make_failure(failure_type="crash"),
            make_failure(failure_type="crash"),
            make_failure(failure_type="unknown_question"),
            make_failure(failure_type="unknown_question"),
        ]
        summarizer = FailureSummarizer(failures)
        summaries = summarizer.summarize()

        counts = [s.count for s in summaries]
        assert counts == sorted(counts, reverse=True)
        assert summaries[0].failure_type == "crash"
        assert summaries[0].count == 3


class TestFailureSummarizerExamples:
    def test_includes_up_to_three_examples(self, make_failure: callable) -> None:
        failures = [make_failure(failure_type="crash") for _ in range(5)]
        summarizer = FailureSummarizer(failures)
        summaries = summarizer.summarize()

        assert len(summaries) == 1
        assert len(summaries[0].examples) == 3

    def test_includes_all_examples_when_less_than_three(
        self, make_failure: callable
    ) -> None:
        failures = [make_failure(failure_type="crash") for _ in range(2)]
        summarizer = FailureSummarizer(failures)
        summaries = summarizer.summarize()

        assert len(summaries[0].examples) == 2


class TestFailureSummarizerEdgeCases:
    def test_empty_failures_returns_empty_list(self) -> None:
        summarizer = FailureSummarizer([])
        summaries = summarizer.summarize()
        assert summaries == []

        top_questions = summarizer.get_top_unknown_questions()
        assert top_questions == []

    def test_failure_missing_question_text_is_skipped(
        self, make_failure: callable
    ) -> None:
        failures = [
            make_failure(question_text="Valid question?"),
            make_failure(details={}),
            make_failure(details={"other_key": "value"}),
        ]
        summarizer = FailureSummarizer(failures)
        groups = summarizer.get_top_unknown_questions()

        assert len(groups) == 1
        assert groups[0][0] == "Valid question?"
        assert groups[0][1] == 1

    def test_all_failures_same_type_returns_single_summary(
        self, make_failure: callable
    ) -> None:
        failures = [make_failure(failure_type="crash") for _ in range(3)]
        summarizer = FailureSummarizer(failures)
        summaries = summarizer.summarize()

        assert len(summaries) == 1
        assert summaries[0].failure_type == "crash"
        assert summaries[0].count == 3

    def test_single_failure_returns_summary_with_count_one(
        self, make_failure: callable
    ) -> None:
        failures = [make_failure(failure_type="timeout")]
        summarizer = FailureSummarizer(failures)
        summaries = summarizer.summarize()

        assert len(summaries) == 1
        assert summaries[0].count == 1


class TestFailureSummarizerContract:
    def test_does_not_modify_input_list(self, make_failure: callable) -> None:
        original_failures = [
            make_failure(failure_type="crash"),
            make_failure(failure_type="timeout"),
        ]
        failures_copy = original_failures.copy()

        summarizer = FailureSummarizer(original_failures)
        summarizer.summarize()
        summarizer.get_top_unknown_questions()

        assert original_failures == failures_copy

    def test_get_top_unknown_questions_respects_n_parameter(
        self, make_failure: callable
    ) -> None:
        distinct_questions = [
            "What is your name?",
            "How many years of experience do you have?",
            "What is your email address?",
            "Are you authorized to work in the US?",
            "What is your phone number?",
            "What is your highest degree?",
            "Do you have a driver's license?",
            "What salary are you expecting?",
            "When can you start?",
            "Why do you want this job?",
            "What are your strengths?",
            "What are your weaknesses?",
            "Describe a challenging project",
            "Where do you see yourself in 5 years?",
            "Do you have any questions for us?",
        ]
        failures = [
            make_failure(question_text=q) for q in distinct_questions
        ]
        summarizer = FailureSummarizer(failures)

        top_5 = summarizer.get_top_unknown_questions(n=5)
        assert len(top_5) == 5

        top_10 = summarizer.get_top_unknown_questions(n=10)
        assert len(top_10) == 10

    def test_grouped_questions_populated_for_unknown_question_type(
        self, make_failure: callable
    ) -> None:
        failures = [
            make_failure(question_text="What is your name?"),
            make_failure(question_text="What's your name?"),
            make_failure(failure_type="crash"),
        ]
        summarizer = FailureSummarizer(failures)
        summaries = summarizer.summarize()

        unknown_summary = next(
            s for s in summaries if s.failure_type == "unknown_question"
        )
        assert len(unknown_summary.grouped_questions) > 0

        crash_summary = next(s for s in summaries if s.failure_type == "crash")
        assert crash_summary.grouped_questions == []
