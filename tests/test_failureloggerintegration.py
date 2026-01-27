"""Tests for FailureLogger integration in answer_engine and form_processor."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.agent.answer_engine import AnswerEngine, _failure_logger as answer_engine_failure_logger
from src.agent.form_processor import FormProcessor, _failure_logger as form_processor_failure_logger
from src.feedback.failure_logger import ApplicationFailure, FailureLogger


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


@pytest.fixture
def mock_page() -> MagicMock:
    page = MagicMock()
    page.url = "https://example.com/form"
    page.raw = MagicMock()
    page.raw.content.return_value = "<html><body>Application Form - Please fill in your details</body></html>"
    page.raw.url = "https://example.com/form"
    page.raw.query_selector.return_value = None
    page.raw.query_selector_all.return_value = []
    return page


@pytest.fixture
def mock_dom_service() -> MagicMock:
    dom_service = MagicMock()
    dom_state = MagicMock()
    dom_state.elementCount = 5
    dom_state.elements = []
    dom_service.extract.return_value = dom_state
    return dom_service


@pytest.fixture
def mock_claude() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_runner() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_tabs() -> MagicMock:
    tabs = MagicMock()
    tabs.get_captured_popup_url.return_value = None
    return tabs


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


class TestFormProcessorFailureLogging:
    """Tests for FailureLogger integration in FormProcessor."""

    def test_logs_timeout_failure(
        self,
        mock_page: MagicMock,
        mock_dom_service: MagicMock,
        mock_claude: MagicMock,
        mock_runner: MagicMock,
        mock_tabs: MagicMock,
        mock_failure_logger: FailureLogger,
    ) -> None:
        """Timeout should be logged as failure."""
        processor = FormProcessor(
            page=mock_page,
            dom_service=mock_dom_service,
            claude=mock_claude,
            runner=mock_runner,
            tabs=mock_tabs,
            profile={},
            resume_path=None,
            timeout_seconds=0,  # Immediate timeout
            max_pages=10,
            job_url="https://example.com/job/123",
            job_title="Engineer",
            company="Tech Corp",
        )

        with patch("src.agent.form_processor._failure_logger", mock_failure_logger):
            with patch("src.agent.form_processor.get_handler", return_value=None):
                with patch.object(processor, "_success_detector") as mock_detector:
                    mock_detector.check.return_value = MagicMock(is_complete=False)
                    mock_detector.reset = MagicMock()
                    result = processor.process("https://example.com/job/123")

        failures = mock_failure_logger.read_all()
        assert len(failures) >= 1
        timeout_failure = next((f for f in failures if f.failure_type == "timeout"), None)
        assert timeout_failure is not None
        assert timeout_failure.job_url == "https://example.com/job/123"
        assert timeout_failure.job_title == "Engineer"
        assert timeout_failure.company == "Tech Corp"

    def test_logs_stuck_loop_failure(
        self,
        mock_page: MagicMock,
        mock_dom_service: MagicMock,
        mock_claude: MagicMock,
        mock_runner: MagicMock,
        mock_tabs: MagicMock,
        mock_failure_logger: FailureLogger,
    ) -> None:
        """Stuck detection should log failure."""
        processor = FormProcessor(
            page=mock_page,
            dom_service=mock_dom_service,
            claude=mock_claude,
            runner=mock_runner,
            tabs=mock_tabs,
            profile={},
            resume_path=None,
            timeout_seconds=300,
            max_pages=10,
            job_url="https://example.com/job/456",
            job_title="Developer",
            company="Dev Corp",
        )

        # Make stuck detection trigger
        with patch("src.agent.form_processor._failure_logger", mock_failure_logger):
            with patch("src.agent.form_processor.get_handler", return_value=None):
                with patch.object(processor, "_success_detector") as mock_detector:
                    with patch.object(processor, "_stuck_detection") as mock_stuck:
                        mock_detector.check.return_value = MagicMock(is_complete=False)
                        mock_detector.reset = MagicMock()
                        mock_stuck.reset = MagicMock()
                        mock_stuck.record_page = MagicMock()
                        mock_stuck.check_stuck.return_value = MagicMock(
                            is_stuck=True,
                            reason="Identical page content 3 times consecutively",
                        )
                        result = processor.process("https://example.com/job/456")

        failures = mock_failure_logger.read_all()
        stuck_failure = next((f for f in failures if f.failure_type == "stuck_loop"), None)
        assert stuck_failure is not None
        assert stuck_failure.job_url == "https://example.com/job/456"
        assert "stuck" in stuck_failure.details["message"].lower() or "identical" in stuck_failure.details["message"].lower()

    def test_captures_page_content_on_failure(
        self,
        mock_page: MagicMock,
        mock_dom_service: MagicMock,
        mock_claude: MagicMock,
        mock_runner: MagicMock,
        mock_tabs: MagicMock,
        mock_failure_logger: FailureLogger,
    ) -> None:
        """Page content should be captured when logging failures."""
        mock_page.raw.content.return_value = "<html><body>Failure page content</body></html>"

        processor = FormProcessor(
            page=mock_page,
            dom_service=mock_dom_service,
            claude=mock_claude,
            runner=mock_runner,
            tabs=mock_tabs,
            profile={},
            resume_path=None,
            timeout_seconds=0,
            max_pages=10,
            job_url="https://example.com/job",
            job_title="Job",
            company="Company",
        )

        with patch("src.agent.form_processor._failure_logger", mock_failure_logger):
            with patch("src.agent.form_processor.get_handler", return_value=None):
                with patch.object(processor, "_success_detector") as mock_detector:
                    mock_detector.check.return_value = MagicMock(is_complete=False)
                    mock_detector.reset = MagicMock()
                    processor.process("https://example.com/job")

        failures = mock_failure_logger.read_all()
        assert len(failures) >= 1
        assert failures[0].page_snapshot is not None
        assert "Failure page content" in failures[0].page_snapshot

    def test_truncates_large_page_content(
        self,
        mock_page: MagicMock,
        mock_dom_service: MagicMock,
        mock_claude: MagicMock,
        mock_runner: MagicMock,
        mock_tabs: MagicMock,
        mock_failure_logger: FailureLogger,
    ) -> None:
        """Large page content should be truncated to 50KB."""
        large_content = "x" * (60 * 1024)
        mock_page.raw.content.return_value = large_content

        processor = FormProcessor(
            page=mock_page,
            dom_service=mock_dom_service,
            claude=mock_claude,
            runner=mock_runner,
            tabs=mock_tabs,
            profile={},
            resume_path=None,
            timeout_seconds=0,
            max_pages=10,
            job_url="https://example.com/job",
            job_title="Job",
            company="Company",
        )

        with patch("src.agent.form_processor._failure_logger", mock_failure_logger):
            with patch("src.agent.form_processor.get_handler", return_value=None):
                with patch.object(processor, "_success_detector") as mock_detector:
                    mock_detector.check.return_value = MagicMock(is_complete=False)
                    mock_detector.reset = MagicMock()
                    processor.process("https://example.com/job")

        failures = mock_failure_logger.read_all()
        assert len(failures) >= 1
        assert len(failures[0].page_snapshot) == 50 * 1024

    def test_page_content_exception_sets_snapshot_to_none(
        self,
        mock_page: MagicMock,
        mock_dom_service: MagicMock,
        mock_claude: MagicMock,
        mock_runner: MagicMock,
        mock_tabs: MagicMock,
        mock_failure_logger: FailureLogger,
    ) -> None:
        """page.content() raising should set page_snapshot to empty/None."""
        mock_page.raw.content.side_effect = Exception("Content fetch failed")

        processor = FormProcessor(
            page=mock_page,
            dom_service=mock_dom_service,
            claude=mock_claude,
            runner=mock_runner,
            tabs=mock_tabs,
            profile={},
            resume_path=None,
            timeout_seconds=0,
            max_pages=10,
            job_url="https://example.com/job",
            job_title="Job",
            company="Company",
        )

        with patch("src.agent.form_processor._failure_logger", mock_failure_logger):
            with patch("src.agent.form_processor.get_handler", return_value=None):
                with patch.object(processor, "_success_detector") as mock_detector:
                    mock_detector.check.return_value = MagicMock(is_complete=False)
                    mock_detector.reset = MagicMock()
                    result = processor.process("https://example.com/job")

        failures = mock_failure_logger.read_all()
        assert len(failures) >= 1
        # Should be None when content() fails
        assert failures[0].page_snapshot is None

    def test_logger_exception_does_not_break_processing(
        self,
        mock_page: MagicMock,
        mock_dom_service: MagicMock,
        mock_claude: MagicMock,
        mock_runner: MagicMock,
        mock_tabs: MagicMock,
    ) -> None:
        """FailureLogger.log() raising should not break form processing."""
        mock_logger = MagicMock()
        mock_logger.log.side_effect = Exception("Logging failed")

        processor = FormProcessor(
            page=mock_page,
            dom_service=mock_dom_service,
            claude=mock_claude,
            runner=mock_runner,
            tabs=mock_tabs,
            profile={},
            resume_path=None,
            timeout_seconds=0,
            max_pages=10,
        )

        with patch("src.agent.form_processor._failure_logger", mock_logger):
            with patch("src.agent.form_processor.get_handler", return_value=None):
                with patch.object(processor, "_success_detector") as mock_detector:
                    mock_detector.check.return_value = MagicMock(is_complete=False)
                    mock_detector.reset = MagicMock()
                    # Should not raise, should return result
                    result = processor.process("https://example.com/job")

        assert result is not None

    def test_empty_job_context_uses_empty_strings(
        self,
        mock_page: MagicMock,
        mock_dom_service: MagicMock,
        mock_claude: MagicMock,
        mock_runner: MagicMock,
        mock_tabs: MagicMock,
        mock_failure_logger: FailureLogger,
    ) -> None:
        """Missing job context should use empty strings."""
        processor = FormProcessor(
            page=mock_page,
            dom_service=mock_dom_service,
            claude=mock_claude,
            runner=mock_runner,
            tabs=mock_tabs,
            profile={},
            resume_path=None,
            timeout_seconds=0,
            max_pages=10,
            # Not providing job_url, job_title, company
        )

        with patch("src.agent.form_processor._failure_logger", mock_failure_logger):
            with patch("src.agent.form_processor.get_handler", return_value=None):
                with patch.object(processor, "_success_detector") as mock_detector:
                    mock_detector.check.return_value = MagicMock(is_complete=False)
                    mock_detector.reset = MagicMock()
                    processor.process("https://example.com/job")

        failures = mock_failure_logger.read_all()
        assert len(failures) >= 1
        assert failures[0].job_url == ""
        assert failures[0].job_title == ""
        assert failures[0].company == ""


class TestStuckDetectionIntegration:
    """Tests for FormProcessorStuckDetection integration."""

    def test_record_page_called_on_each_iteration(
        self,
        mock_page: MagicMock,
        mock_dom_service: MagicMock,
        mock_claude: MagicMock,
        mock_runner: MagicMock,
        mock_tabs: MagicMock,
    ) -> None:
        """record_page should be called on each processing iteration."""
        processor = FormProcessor(
            page=mock_page,
            dom_service=mock_dom_service,
            claude=mock_claude,
            runner=mock_runner,
            tabs=mock_tabs,
            profile={},
            resume_path=None,
            timeout_seconds=300,
            max_pages=3,
        )

        call_count = 0
        original_record_page = processor._stuck_detection.record_page

        def counting_record_page(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            # After 2 calls, report stuck to end the loop
            if call_count >= 2:
                processor._stuck_detection.check_stuck = MagicMock(
                    return_value=MagicMock(is_stuck=True, reason="Test stuck")
                )

        with patch("src.agent.form_processor.get_handler", return_value=None):
            with patch("src.agent.form_processor._failure_logger"):
                with patch.object(processor, "_success_detector") as mock_detector:
                    with patch.object(processor._stuck_detection, "record_page", side_effect=counting_record_page):
                        mock_detector.check.return_value = MagicMock(is_complete=False)
                        mock_detector.reset = MagicMock()
                        processor.process("https://example.com/job")

        assert call_count >= 1

    def test_check_stuck_called_on_each_iteration(
        self,
        mock_page: MagicMock,
        mock_dom_service: MagicMock,
        mock_claude: MagicMock,
        mock_runner: MagicMock,
        mock_tabs: MagicMock,
    ) -> None:
        """check_stuck should be called to detect stuck state."""
        processor = FormProcessor(
            page=mock_page,
            dom_service=mock_dom_service,
            claude=mock_claude,
            runner=mock_runner,
            tabs=mock_tabs,
            profile={},
            resume_path=None,
            timeout_seconds=300,
            max_pages=3,
        )

        check_stuck_calls = []

        def tracking_check_stuck() -> MagicMock:
            check_stuck_calls.append(1)
            # End after a few calls
            if len(check_stuck_calls) >= 2:
                return MagicMock(is_stuck=True, reason="Test stuck")
            return MagicMock(is_stuck=False)

        with patch("src.agent.form_processor.get_handler", return_value=None):
            with patch("src.agent.form_processor._failure_logger"):
                with patch.object(processor, "_success_detector") as mock_detector:
                    with patch.object(processor._stuck_detection, "check_stuck", side_effect=tracking_check_stuck):
                        with patch.object(processor._stuck_detection, "record_page"):
                            mock_detector.check.return_value = MagicMock(is_complete=False)
                            mock_detector.reset = MagicMock()
                            processor.process("https://example.com/job")

        assert len(check_stuck_calls) >= 1

    def test_returns_early_when_stuck_detected(
        self,
        mock_page: MagicMock,
        mock_dom_service: MagicMock,
        mock_claude: MagicMock,
        mock_runner: MagicMock,
        mock_tabs: MagicMock,
    ) -> None:
        """Processing should return early when stuck is detected."""
        processor = FormProcessor(
            page=mock_page,
            dom_service=mock_dom_service,
            claude=mock_claude,
            runner=mock_runner,
            tabs=mock_tabs,
            profile={},
            resume_path=None,
            timeout_seconds=300,
            max_pages=10,
        )

        with patch("src.agent.form_processor.get_handler", return_value=None):
            with patch("src.agent.form_processor._failure_logger"):
                with patch.object(processor, "_success_detector") as mock_detector:
                    with patch.object(processor._stuck_detection, "check_stuck") as mock_check:
                        with patch.object(processor._stuck_detection, "record_page"):
                            mock_detector.check.return_value = MagicMock(is_complete=False)
                            mock_detector.reset = MagicMock()
                            mock_check.return_value = MagicMock(
                                is_stuck=True,
                                reason="Stuck in loop",
                            )
                            result = processor.process("https://example.com/job")

        from src.agent.models import ApplicationStatus
        assert result.status == ApplicationStatus.STUCK
        assert "Stuck" in result.message or "loop" in result.message.lower()


class TestModuleLevelFailureLogger:
    """Tests for module-level FailureLogger instances."""

    def test_answer_engine_has_module_level_logger(self) -> None:
        """answer_engine should have a module-level FailureLogger."""
        assert answer_engine_failure_logger is not None
        assert isinstance(answer_engine_failure_logger, FailureLogger)

    def test_form_processor_has_module_level_logger(self) -> None:
        """form_processor should have a module-level FailureLogger."""
        assert form_processor_failure_logger is not None
        assert isinstance(form_processor_failure_logger, FailureLogger)
