from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.feedback.failure_summarizer import FailureSummary


@dataclass
class FixSuggestion:
    target_file: str
    fix_type: str
    description: str
    suggested_content: str
    failure_count: int


class ConfigSuggester:
    def suggest(self, summaries: list[FailureSummary]) -> list[FixSuggestion]:
        if not summaries:
            return []

        suggestions: list[FixSuggestion] = []

        for summary in summaries:
            if summary.count == 0:
                continue

            suggestion = self._create_suggestion(summary)
            if suggestion:
                suggestions.append(suggestion)

        suggestions.sort(key=lambda s: s.failure_count, reverse=True)
        return suggestions

    def _create_suggestion(self, summary: FailureSummary) -> FixSuggestion | None:
        failure_type = summary.failure_type

        if failure_type == "unknown_question":
            return self._suggest_unknown_question(summary)
        elif failure_type == "react_select_fail":
            return self._suggest_react_select(summary)
        elif failure_type == "validation_error":
            return self._suggest_validation_error(summary)
        elif failure_type == "stuck_loop":
            return None
        elif failure_type == "timeout":
            return self._suggest_timeout(summary)
        elif failure_type == "crash":
            return self._suggest_crash(summary)

        return None

    def _suggest_unknown_question(self, summary: FailureSummary) -> FixSuggestion:
        patterns: list[str] = []
        example_questions: list[str] = []

        for canonical, count, _ in summary.grouped_questions:
            pattern = self._generate_regex_pattern(canonical)
            patterns.append(f"  r'{pattern}': 'config_key_{len(patterns) + 1}',")
            example_questions.append(f"  # Example: {canonical!r} (count: {count})")

        suggested_content = "# Add to QUESTION_PATTERNS:\n"
        suggested_content += "\n".join(example_questions) + "\n"
        suggested_content += "QUESTION_PATTERNS = {\n"
        suggested_content += "\n".join(patterns) + "\n"
        suggested_content += "}"

        return FixSuggestion(
            target_file="src/agent/answer_engine.py",
            fix_type="add_pattern",
            description=f"Add regex patterns for {len(summary.grouped_questions)} unknown question types",
            suggested_content=suggested_content,
            failure_count=summary.count,
        )

    def _suggest_react_select(self, summary: FailureSummary) -> FixSuggestion:
        selectors: list[str] = []

        for example in summary.examples:
            if isinstance(example.details, dict):
                selector = example.details.get("selector", "unknown")
                if selector not in selectors:
                    selectors.append(selector)

        suggested_content = "# Add handler for react-select components:\n"
        suggested_content += "# Selectors encountered:\n"
        for selector in selectors:
            suggested_content += f"#   {selector}\n"
        suggested_content += "\n# Example handler pattern:\n"
        suggested_content += "# await handle_react_select(page, selector, value)"

        return FixSuggestion(
            target_file="src/agent/form_processor.py",
            fix_type="add_handler",
            description=f"Add react-select handler for {len(selectors)} selector patterns",
            suggested_content=suggested_content,
            failure_count=summary.count,
        )

    def _suggest_validation_error(self, summary: FailureSummary) -> FixSuggestion:
        field_info: list[str] = []

        for example in summary.examples:
            if isinstance(example.details, dict):
                field_selector = example.details.get("field_selector", "unknown")
                error_message = example.details.get("error_message", "unknown")
                field_info.append(f"  Field: {field_selector}, Error: {error_message}")

        suggested_content = "# Validation errors requiring manual review:\n"
        suggested_content += "\n".join(field_info)

        return FixSuggestion(
            target_file="src/agent/form_processor.py",
            fix_type="investigate",
            description=f"Investigate {summary.count} validation errors",
            suggested_content=suggested_content,
            failure_count=summary.count,
        )

    def _suggest_timeout(self, summary: FailureSummary) -> FixSuggestion:
        timeout_info: list[str] = []

        for example in summary.examples:
            if isinstance(example.details, dict):
                page_url = example.details.get("page_url", example.job_url)
                last_action = example.details.get("last_action", "unknown")
                timeout_info.append(f"  URL: {page_url}, Last action: {last_action}")

        suggested_content = "# Timeout occurrences requiring investigation:\n"
        suggested_content += "\n".join(timeout_info)

        return FixSuggestion(
            target_file="src/agent/form_processor.py",
            fix_type="investigate",
            description=f"Investigate {summary.count} timeout failures",
            suggested_content=suggested_content,
            failure_count=summary.count,
        )

    def _suggest_crash(self, summary: FailureSummary) -> FixSuggestion:
        crash_info: list[str] = []

        for example in summary.examples:
            if isinstance(example.details, dict):
                exception_type = example.details.get("exception_type", "unknown")
                exception_message = example.details.get("exception_message", "unknown")
                crash_info.append(f"  {exception_type}: {exception_message}")

        suggested_content = "# Crash exceptions requiring investigation:\n"
        suggested_content += "\n".join(crash_info)

        return FixSuggestion(
            target_file="src/agent/form_processor.py",
            fix_type="investigate",
            description=f"Investigate {summary.count} crash failures",
            suggested_content=suggested_content,
            failure_count=summary.count,
        )

    def _generate_regex_pattern(self, question_text: str) -> str:
        escaped = re.escape(question_text)
        pattern = re.sub(r"\\d+|\d+", r"\\d+", escaped)
        return pattern
