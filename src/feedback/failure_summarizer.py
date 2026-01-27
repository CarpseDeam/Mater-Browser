from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from src.feedback.failure_logger import ApplicationFailure


@dataclass
class FailureSummary:
    failure_type: str
    count: int
    examples: list[ApplicationFailure]
    grouped_questions: list[tuple[str, int, list[str]]] = field(default_factory=list)


class FailureSummarizer:
    def __init__(self, failures: list[ApplicationFailure]) -> None:
        self._failures = failures

    def summarize(self) -> list[FailureSummary]:
        if not self._failures:
            return []

        grouped: dict[str, list[ApplicationFailure]] = {}
        for failure in self._failures:
            grouped.setdefault(failure.failure_type, []).append(failure)

        summaries: list[FailureSummary] = []
        for failure_type, type_failures in grouped.items():
            examples = type_failures[:3]
            grouped_questions: list[tuple[str, int, list[str]]] = []

            if failure_type == "unknown_question":
                grouped_questions = self._group_questions(type_failures)

            summaries.append(
                FailureSummary(
                    failure_type=failure_type,
                    count=len(type_failures),
                    examples=examples,
                    grouped_questions=grouped_questions,
                )
            )

        summaries.sort(key=lambda s: s.count, reverse=True)
        return summaries

    def get_top_unknown_questions(
        self, n: int = 10
    ) -> list[tuple[str, int, list[str]]]:
        unknown_failures = [
            f for f in self._failures if f.failure_type == "unknown_question"
        ]
        if not unknown_failures:
            return []

        grouped = self._group_questions(unknown_failures)
        return grouped[:n]

    def _group_questions(
        self, failures: list[ApplicationFailure]
    ) -> list[tuple[str, int, list[str]]]:
        questions: list[str] = []
        for failure in failures:
            if not isinstance(failure.details, dict):
                continue
            question_text = failure.details.get("question") or failure.details.get("question_text")
            if question_text and isinstance(question_text, str):
                questions.append(question_text)

        if not questions:
            return []

        groups: list[list[str]] = []
        for question in questions:
            matched = False
            for group in groups:
                representative = group[0]
                ratio = SequenceMatcher(None, question, representative).ratio()
                if ratio > 0.7:
                    group.append(question)
                    matched = True
                    break
            if not matched:
                groups.append([question])

        result: list[tuple[str, int, list[str]]] = []
        for group in groups:
            canonical = min(group, key=len)
            similar = [q for q in group if q != canonical]
            result.append((canonical, len(group), similar))

        result.sort(key=lambda x: x[1], reverse=True)
        return result
