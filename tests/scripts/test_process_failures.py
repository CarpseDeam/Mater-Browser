"""Tests for process_failures CLI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

import pytest

from scripts.process_failures import main, generate_prompt, print_summary, clear_addressed
from src.feedback.failure_logger import ApplicationFailure
from src.feedback.failure_summarizer import FailureSummary
from src.feedback.config_suggester import FixSuggestion


@pytest.fixture
def temp_log_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "failures.jsonl"


@pytest.fixture
def sample_failure() -> dict[str, Any]:
    return {
        "timestamp": "2024-01-15T10:30:00",
        "job_url": "https://example.com/job/123",
        "job_title": "Software Engineer",
        "company": "TechCorp",
        "failure_type": "unknown_question",
        "details": {"question_text": "What is your expected salary?"},
        "page_snapshot": None,
        "addressed": False,
    }


@pytest.fixture
def sample_failures_jsonl(temp_log_path: Path, sample_failure: dict[str, Any]) -> Path:
    temp_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_log_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(sample_failure) + "\n")
        failure2 = sample_failure.copy()
        failure2["timestamp"] = "2024-01-15T11:00:00"
        failure2["failure_type"] = "react_select_fail"
        failure2["details"] = {"selector": ".react-select"}
        f.write(json.dumps(failure2) + "\n")
    return temp_log_path


class TestSummaryCommand:
    def test_summary_prints_failure_types_with_counts(
        self, sample_failures_jsonl: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = main(["--summary", "--log-path", str(sample_failures_jsonl)])

        assert result == 0
        captured = capsys.readouterr()
        assert "unknown_question" in captured.out
        assert "react_select_fail" in captured.out

    def test_summary_shows_top_unknown_questions(
        self, temp_log_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        temp_log_path.parent.mkdir(parents=True, exist_ok=True)
        failures = []
        for i in range(6):
            failures.append({
                "timestamp": f"2024-01-15T10:{i:02d}:00",
                "job_url": "https://example.com/job/123",
                "job_title": "Engineer",
                "company": "Corp",
                "failure_type": "unknown_question",
                "details": {"question_text": f"Question number {i}"},
                "page_snapshot": None,
                "addressed": False,
            })

        with open(temp_log_path, "w", encoding="utf-8") as f:
            for failure in failures:
                f.write(json.dumps(failure) + "\n")

        result = main(["--summary", "--log-path", str(temp_log_path)])

        assert result == 0
        captured = capsys.readouterr()
        assert "Top unknown questions" in captured.out

    def test_default_shows_summary(
        self, sample_failures_jsonl: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = main(["--log-path", str(sample_failures_jsonl)])

        assert result == 0
        captured = capsys.readouterr()
        assert "Failure Type" in captured.out


class TestGeneratePromptCommand:
    def test_generate_prompt_outputs_markdown(
        self, sample_failures_jsonl: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = main(["--generate-prompt", "--log-path", str(sample_failures_jsonl)])

        assert result == 0
        captured = capsys.readouterr()
        assert "# Fix Suggestions" in captured.out
        assert "**Target file:**" in captured.out

    def test_generate_prompt_function(self) -> None:
        suggestions = [
            FixSuggestion(
                target_file="src/test.py",
                fix_type="add_pattern",
                description="Add pattern for test",
                suggested_content="# test content",
                failure_count=5,
            )
        ]

        output = generate_prompt(suggestions)

        assert "# Fix Suggestions" in output
        assert "src/test.py" in output
        assert "add_pattern" in output
        assert "# test content" in output


class TestAutoFixCommand:
    def test_auto_fix_posts_to_bridge(
        self, sample_failures_jsonl: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("scripts.process_failures.requests.post", return_value=mock_response) as mock_post:
            result = main(["--auto-fix", "--log-path", str(sample_failures_jsonl)])

        assert result == 0
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://localhost:5001/dispatch"
        assert "spec" in call_args[1]["json"]
        assert "project_path" in call_args[1]["json"]
        captured = capsys.readouterr()
        assert "Successfully dispatched" in captured.out

    def test_auto_fix_handles_connection_error(
        self, sample_failures_jsonl: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import requests

        with patch(
            "scripts.process_failures.requests.post",
            side_effect=requests.ConnectionError("Connection refused"),
        ):
            result = main(["--auto-fix", "--log-path", str(sample_failures_jsonl)])

        assert result == 1
        captured = capsys.readouterr()
        assert "Could not connect" in captured.out


class TestClearAddressedCommand:
    def test_clear_addressed_removes_addressed_entries(
        self, temp_log_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        temp_log_path.parent.mkdir(parents=True, exist_ok=True)
        entries = [
            {
                "timestamp": "2024-01-15T10:00:00",
                "job_url": "https://example.com/1",
                "job_title": "Job 1",
                "company": "Corp",
                "failure_type": "crash",
                "details": {},
                "addressed": True,
            },
            {
                "timestamp": "2024-01-15T11:00:00",
                "job_url": "https://example.com/2",
                "job_title": "Job 2",
                "company": "Corp",
                "failure_type": "crash",
                "details": {},
                "addressed": False,
            },
        ]

        with open(temp_log_path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        result = main(["--clear-addressed", "--log-path", str(temp_log_path)])

        assert result == 0
        with open(temp_log_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["timestamp"] == "2024-01-15T11:00:00"

    def test_clear_addressed_rewrites_jsonl(
        self, temp_log_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        temp_log_path.parent.mkdir(parents=True, exist_ok=True)
        entries = [
            {
                "timestamp": "2024-01-15T10:00:00",
                "job_url": "https://example.com/1",
                "job_title": "Job 1",
                "company": "Corp",
                "failure_type": "crash",
                "details": {},
                "addressed": True,
            },
        ]

        with open(temp_log_path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        result = main(["--clear-addressed", "--log-path", str(temp_log_path)])

        assert result == 0
        captured = capsys.readouterr()
        assert "0 entries remaining" in captured.out


class TestEdgeCases:
    def test_no_failures_file_prints_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        nonexistent = tmp_path / "nonexistent" / "failures.jsonl"

        result = main(["--log-path", str(nonexistent)])

        assert result == 0
        captured = capsys.readouterr()
        assert "No failures logged yet" in captured.out

    def test_empty_failures_file_prints_message(
        self, temp_log_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        temp_log_path.parent.mkdir(parents=True, exist_ok=True)
        temp_log_path.touch()

        result = main(["--log-path", str(temp_log_path)])

        assert result == 0
        captured = capsys.readouterr()
        assert "No failures logged yet" in captured.out

    def test_all_failures_addressed_prints_message(
        self, temp_log_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        temp_log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": "2024-01-15T10:00:00",
            "job_url": "https://example.com/1",
            "job_title": "Job 1",
            "company": "Corp",
            "failure_type": "crash",
            "details": {},
            "addressed": True,
        }

        with open(temp_log_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        result = main(["--log-path", str(temp_log_path)])

        assert result == 0
        captured = capsys.readouterr()
        assert "No failures logged yet" in captured.out

    def test_clear_addressed_no_file_prints_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        nonexistent = tmp_path / "nonexistent" / "failures.jsonl"

        result = main(["--clear-addressed", "--log-path", str(nonexistent)])

        assert result == 0
        captured = capsys.readouterr()
        assert "No failures logged yet" in captured.out


class TestExitCodes:
    def test_success_returns_zero(
        self, sample_failures_jsonl: Path
    ) -> None:
        result = main(["--summary", "--log-path", str(sample_failures_jsonl)])
        assert result == 0

    def test_error_returns_one(
        self, sample_failures_jsonl: Path
    ) -> None:
        import requests

        with patch(
            "scripts.process_failures.requests.post",
            side_effect=requests.ConnectionError("Connection refused"),
        ):
            result = main(["--auto-fix", "--log-path", str(sample_failures_jsonl)])

        assert result == 1


class TestArgparseUsage:
    def test_uses_argparse(self) -> None:
        import argparse
        from scripts import process_failures

        with patch.object(argparse.ArgumentParser, "parse_args") as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                summary=False,
                generate_prompt=False,
                auto_fix=False,
                clear_addressed=False,
                log_path=Path("data/failures.jsonl"),
            )
            with patch.object(process_failures.FailureLogger, "read_all", return_value=[]):
                main([])

            mock_parse.assert_called_once()
