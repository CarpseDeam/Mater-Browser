"""Tests for FailureLogger integration in answer_engine."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agent.answer_engine import AnswerEngine, _failure_logger as answer_engine_failure_logger
from src.feedback.failure_logger import FailureLogger


@pytest.fixture
def temp_log_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "failures.jsonl"


@pytest.fixture
def mock_failure_logger(temp_log_path: Path) -> FailureLogger:
    return FailureLogger(log_path=temp_log_path)


@pytest.fixture
def answer_engine(tmp_path: Path) -> AnswerEngine:
    config_path = tmp_path / "answers.yaml"
    config_path.write_text("personal:\n  first_name: John\n")
    return AnswerEngine(config_path=config_path)


class TestAnswerEngineFailureLogging:
    """Tests for FailureLogger integration in AnswerEngine."""

    def test_logs_unknown_question_failure(
        self, answer_engine: AnswerEngine, mock_failure_logger: FailureLogger, temp_log_path: Path
    ) -> None:
        """Unknown question should be logged as failure."""
        with patch("src.agent.answer_engine._failure_logger", mock_failure_logger):
            result = answer_engine.get_answer(
                "What is your favorite color?",
                "text",
                job_url="https://example.com/job/123",
                job_title="Software Engineer",
                company="Example Corp",
            )

        assert result is None
        failures = mock_failure_logger.read_all()
        assert len(failures) == 1
        assert failures[0].failure_type == "unknown_question"
        assert failures[0].job_url == "https://example.com/job/123"
        assert failures[0].job_title == "Software Engineer"
        assert failures[0].company == "Example Corp"
        assert failures[0].details["question"] == "What is your favorite color?"

    def test_uses_iso_timestamp(
        self, answer_engine: AnswerEngine, mock_failure_logger: FailureLogger, temp_log_path: Path
    ) -> None:
        """Failure logs should use ISO timestamp format."""
        with patch("src.agent.answer_engine._failure_logger", mock_failure_logger):
            answer_engine.get_answer("unknown question", "text")

        failures = mock_failure_logger.read_all()
        assert len(failures) == 1
        # Verify ISO format by parsing
        datetime.fromisoformat(failures[0].timestamp)

    def test_captures_page_snapshot(
        self, answer_engine: AnswerEngine, mock_failure_logger: FailureLogger
    ) -> None:
        """Page snapshot should be captured when provided."""
        snapshot = "<html><body>Test page</body></html>"
        with patch("src.agent.answer_engine._failure_logger", mock_failure_logger):
            answer_engine.get_answer(
                "unknown question",
                "text",
                page_snapshot=snapshot,
            )

        failures = mock_failure_logger.read_all()
        assert failures[0].page_snapshot == snapshot

    def test_truncates_large_page_snapshot(
        self, answer_engine: AnswerEngine, mock_failure_logger: FailureLogger
    ) -> None:
        """Page snapshots larger than 50KB should be truncated."""
        large_snapshot = "x" * (60 * 1024)  # 60KB
        with patch("src.agent.answer_engine._failure_logger", mock_failure_logger):
            answer_engine.get_answer(
                "unknown question",
                "text",
                page_snapshot=large_snapshot,
            )

        failures = mock_failure_logger.read_all()
        assert len(failures[0].page_snapshot) == 50 * 1024

    def test_no_log_when_answer_found(
        self, answer_engine: AnswerEngine, mock_failure_logger: FailureLogger
    ) -> None:
        """No failure should be logged when answer is found."""
        with patch("src.agent.answer_engine._failure_logger", mock_failure_logger):
            result = answer_engine.get_answer("What is your first name?", "text")

        assert result == "John"
        failures = mock_failure_logger.read_all()
        assert len(failures) == 0

    def test_empty_job_context_uses_empty_strings(
        self, answer_engine: AnswerEngine, mock_failure_logger: FailureLogger
    ) -> None:
        """Missing job context should use empty strings."""
        with patch("src.agent.answer_engine._failure_logger", mock_failure_logger):
            answer_engine.get_answer("unknown question", "text")

        failures = mock_failure_logger.read_all()
        assert failures[0].job_url == ""
        assert failures[0].job_title == ""
        assert failures[0].company == ""

    def test_logger_exception_does_not_break_get_answer(
        self, answer_engine: AnswerEngine
    ) -> None:
        """FailureLogger.log() raising should not break form filling."""
        mock_logger = MagicMock()
        mock_logger.log.side_effect = Exception("Logging failed")

        with patch("src.agent.answer_engine._failure_logger", mock_logger):
            result = answer_engine.get_answer("unknown question", "text")

        assert result is None  # Should still return None, not raise

    def test_page_snapshot_none_when_not_provided(
        self, answer_engine: AnswerEngine, mock_failure_logger: FailureLogger
    ) -> None:
        """Page snapshot should be None when not provided."""
        with patch("src.agent.answer_engine._failure_logger", mock_failure_logger):
            answer_engine.get_answer("unknown question", "text")

        failures = mock_failure_logger.read_all()
        assert failures[0].page_snapshot is None


class TestModuleLevelFailureLogger:
    """Tests for module-level FailureLogger instances."""

    def test_answer_engine_has_module_level_logger(self) -> None:
        """answer_engine should have a module-level FailureLogger."""
        assert answer_engine_failure_logger is not None
        assert isinstance(answer_engine_failure_logger, FailureLogger)
