"""CLI entry point for the failure feedback system."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import requests

from src.feedback.failure_logger import FailureLogger, DEFAULT_LOG_PATH
from src.feedback.failure_summarizer import FailureSummarizer
from src.feedback.config_suggester import ConfigSuggester, FixSuggestion

if TYPE_CHECKING:
    from src.feedback.failure_summarizer import FailureSummary

BRIDGE_URL = "http://localhost:5001/dispatch"


def print_summary(summaries: list[FailureSummary]) -> None:
    print(f"{'Failure Type':<20} {'Count':<8} {'Top Example'}")
    print("-" * 70)

    for summary in summaries:
        example_text = ""
        if summary.examples:
            ex = summary.examples[0]
            example_text = f"{ex.company} - {ex.job_title}"[:40]

        print(f"{summary.failure_type:<20} {summary.count:<8} {example_text}")

        if summary.failure_type == "unknown_question" and summary.grouped_questions:
            print("\n  Top unknown questions:")
            for canonical, count, _ in summary.grouped_questions[:5]:
                truncated = canonical[:60] + "..." if len(canonical) > 60 else canonical
                print(f"    - ({count}x) {truncated}")
            print()


def generate_prompt(suggestions: list[FixSuggestion]) -> str:
    lines = ["# Fix Suggestions for Failure Feedback System", ""]

    for i, suggestion in enumerate(suggestions, 1):
        lines.append(f"## {i}. {suggestion.fix_type}: {suggestion.description}")
        lines.append(f"**Target file:** `{suggestion.target_file}`")
        lines.append(f"**Failure count:** {suggestion.failure_count}")
        lines.append("")
        lines.append("```")
        lines.append(suggestion.suggested_content)
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def auto_fix(suggestions: list[FixSuggestion], project_path: Path) -> int:
    spec_content = generate_prompt(suggestions)

    payload = {
        "spec": spec_content,
        "project_path": str(project_path.resolve()),
    }

    try:
        response = requests.post(BRIDGE_URL, json=payload, timeout=30)
        response.raise_for_status()
        print("Successfully dispatched fix request to claude-code-bridge")
        return 0
    except requests.ConnectionError:
        print(f"Error: Could not connect to claude-code-bridge at {BRIDGE_URL}")
        print("Make sure the bridge server is running.")
        return 1
    except requests.RequestException as e:
        print(f"Error dispatching to bridge: {e}")
        return 1


def clear_addressed(log_path: Path) -> int:
    if not log_path.exists():
        print("No failures logged yet")
        return 0

    lines_kept = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if not data.get("addressed", False):
                    lines_kept.append(line)
            except json.JSONDecodeError:
                lines_kept.append(line)

    with open(log_path, "w", encoding="utf-8") as f:
        for line in lines_kept:
            f.write(line + "\n")

    print(f"Cleared addressed failures. {len(lines_kept)} entries remaining.")
    return 0


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Process and analyze application failures"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print top failures by type with counts",
    )
    parser.add_argument(
        "--generate-prompt",
        action="store_true",
        help="Generate markdown spec for Claude Code dispatch",
    )
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Auto-dispatch fixes via HTTP to claude-code-bridge server",
    )
    parser.add_argument(
        "--clear-addressed",
        action="store_true",
        help="Remove addressed failures from log",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to failures.jsonl file",
    )

    parsed = parser.parse_args(args)
    logger = FailureLogger(parsed.log_path)

    if parsed.clear_addressed:
        return clear_addressed(parsed.log_path)

    failures = logger.read_all(include_addressed=False)

    if not failures:
        print("No failures logged yet")
        return 0

    summarizer = FailureSummarizer(failures)
    summaries = summarizer.summarize()

    if not summaries:
        print("No unaddressed failures")
        return 0

    if parsed.generate_prompt or parsed.auto_fix:
        suggester = ConfigSuggester()
        suggestions = suggester.suggest(summaries)

        if not suggestions:
            print("No fix suggestions available")
            return 0

        if parsed.generate_prompt:
            print(generate_prompt(suggestions))
            return 0

        if parsed.auto_fix:
            return auto_fix(suggestions, parsed.log_path.parent.parent)

    print_summary(summaries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
