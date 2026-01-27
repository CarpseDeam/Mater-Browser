from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import httpx

from src.feedback.auto_repairer import AutoRepairer, BRIDGE_URL
from src.feedback.failure_logger import ApplicationFailure, FailureLogger


@pytest.fixture
def temp_log_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "failures.jsonl"


@pytest.fixture
def repairer(temp_log_path: Path) -> AutoRepairer:
    r = AutoRepairer(threshold=3, cooldown_minutes=10)
    r._failure_logger = FailureLogger(log_path=temp_log_path)
    return r


@pytest.fixture
def sample_failure() -> ApplicationFailure:
    return ApplicationFailure(
        timestamp=datetime.now().isoformat(),
        job_url="https://example.com/job/123",
        job_title="Software Engineer",
        company="Example Corp",
        failure_type="unknown_question",
        details={
            "question_text": "What is your salary expectation?",
            "field_type": "text",
            "field_id": "salary",
            "field_selector": "#salary-input",
            "page_url": "https://example.com/apply",
        },
        page_snapshot="<html>...</html>",
        addressed=False,
    )


def make_failure(timestamp: str, failure_type: str = "unknown_question") -> ApplicationFailure:
    return ApplicationFailure(
        timestamp=timestamp,
        job_url="https://example.com/job/123",
        job_title="Software Engineer",
        company="Example Corp",
        failure_type=failure_type,
        details={"question_text": "What is your salary?"},
        addressed=False,
    )


class TestTrackFailureCount:
    def test_record_failure_increments_count(
        self, repairer: AutoRepairer, sample_failure: ApplicationFailure
    ) -> None:
        assert repairer._failure_count == 0
        repairer.record_failure(sample_failure)
        assert repairer._failure_count == 1
        repairer.record_failure(sample_failure)
        assert repairer._failure_count == 2

    def test_record_failure_logs_to_file(
        self, repairer: AutoRepairer, sample_failure: ApplicationFailure
    ) -> None:
        repairer.record_failure(sample_failure)
        failures = repairer._failure_logger.read_all()
        assert len(failures) == 1


class TestThresholdTrigger:
    def test_maybe_repair_returns_false_below_threshold(
        self, repairer: AutoRepairer, sample_failure: ApplicationFailure
    ) -> None:
        repairer.record_failure(sample_failure)
        repairer.record_failure(sample_failure)
        assert repairer._failure_count == 2
        assert repairer.maybe_repair() is False

    def test_maybe_repair_returns_true_at_threshold(
        self, repairer: AutoRepairer
    ) -> None:
        for i in range(3):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}"))

        with patch.object(repairer, "_dispatch_repair_sync"):
            result = repairer.maybe_repair()
        assert result is True


class TestCooldown:
    def test_cooldown_prevents_immediate_second_repair(
        self, repairer: AutoRepairer
    ) -> None:
        for i in range(3):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}"))

        with patch.object(repairer, "_dispatch_repair_sync"):
            assert repairer.maybe_repair() is True

        repairer._failure_count = 5
        assert repairer.maybe_repair() is False

    def test_cooldown_expires_after_period(
        self, repairer: AutoRepairer
    ) -> None:
        repairer._cooldown_minutes = 0

        for i in range(3):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}"))

        with patch.object(repairer, "_dispatch_repair_sync"):
            assert repairer.maybe_repair() is True

        repairer._failure_count = 5
        repairer._last_repair_time = time.time() - 1

        for i in range(3, 6):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}"))

        with patch.object(repairer, "_dispatch_repair_sync"):
            assert repairer.maybe_repair() is True


class TestDispatchLogic:
    def test_dispatch_posts_to_bridge(
        self, repairer: AutoRepairer
    ) -> None:
        for i in range(3):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}"))

        failures = repairer._failure_logger.read_all()
        spec = repairer._generate_spec(failures)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        with patch("src.feedback.auto_repairer.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = MagicMock(return_value=mock_response)
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_client

            repairer._dispatch_repair_sync(spec, failures)

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == BRIDGE_URL
            payload = call_args[1]["json"]
            assert "content" in payload
            assert "project_path" in payload

    def test_dispatch_marks_failures_addressed_on_success(
        self, repairer: AutoRepairer
    ) -> None:
        for i in range(3):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}"))

        failures = repairer._failure_logger.read_all()
        spec = repairer._generate_spec(failures)

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("src.feedback.auto_repairer.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = MagicMock(return_value=mock_response)
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_client

            repairer._dispatch_repair_sync(spec, failures)

        remaining = repairer._failure_logger.read_all(include_addressed=False)
        assert len(remaining) == 0


class TestLogging:
    def test_logs_when_repair_triggered(
        self, repairer: AutoRepairer, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging
        caplog.set_level(logging.INFO)

        for i in range(3):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}"))

        with patch.object(repairer, "_dispatch_repair_sync"):
            repairer.maybe_repair()

        assert "Triggering auto-repair" in caplog.text

    def test_logs_dispatch_result(
        self, repairer: AutoRepairer, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging
        caplog.set_level(logging.INFO)

        for i in range(3):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}"))

        failures = repairer._failure_logger.read_all()
        spec = repairer._generate_spec(failures)

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("src.feedback.auto_repairer.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = MagicMock(return_value=mock_response)
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_client

            repairer._dispatch_repair_sync(spec, failures)

        assert "dispatched successfully" in caplog.text


class TestBridgeErrors:
    def test_bridge_not_running_logs_warning(
        self, repairer: AutoRepairer, caplog: pytest.LogCaptureFixture
    ) -> None:
        for i in range(3):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}"))

        failures = repairer._failure_logger.read_all()
        spec = repairer._generate_spec(failures)

        with patch("src.feedback.auto_repairer.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = MagicMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_client

            repairer._dispatch_repair_sync(spec, failures)

        assert "Bridge server not available" in caplog.text

    def test_bridge_timeout_logs_warning(
        self, repairer: AutoRepairer, caplog: pytest.LogCaptureFixture
    ) -> None:
        for i in range(3):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}"))

        failures = repairer._failure_logger.read_all()
        spec = repairer._generate_spec(failures)

        with patch("src.feedback.auto_repairer.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = MagicMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_client

            repairer._dispatch_repair_sync(spec, failures)

        assert "timed out" in caplog.text

    def test_bridge_error_does_not_crash(
        self, repairer: AutoRepairer
    ) -> None:
        for i in range(3):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}"))

        failures = repairer._failure_logger.read_all()
        spec = repairer._generate_spec(failures)

        with patch("src.feedback.auto_repairer.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = MagicMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_client

            repairer._dispatch_repair_sync(spec, failures)


class TestAsyncExecution:
    def test_maybe_repair_does_not_block(
        self, repairer: AutoRepairer
    ) -> None:
        for i in range(3):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}"))

        with patch.object(repairer, "_dispatch_repair_sync") as mock_dispatch:
            start = time.time()
            result = repairer.maybe_repair()
            elapsed = time.time() - start

            assert result is True
            assert elapsed < 0.5


class TestReset:
    def test_reset_clears_failure_count(
        self, repairer: AutoRepairer, sample_failure: ApplicationFailure
    ) -> None:
        repairer.record_failure(sample_failure)
        repairer.record_failure(sample_failure)
        assert repairer._failure_count == 2

        repairer.reset()
        assert repairer._failure_count == 0


class TestEdgeCases:
    def test_no_unaddressed_failures_skips_repair(
        self, repairer: AutoRepairer, temp_log_path: Path
    ) -> None:
        repairer._failure_count = 5

        assert repairer.maybe_repair() is False

    def test_all_failures_same_type_generates_single_spec(
        self, repairer: AutoRepairer
    ) -> None:
        for i in range(5):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}", "unknown_question"))

        failures = repairer._failure_logger.read_all()
        spec = repairer._generate_spec(failures)

        assert len(spec.suggestions) == 1
        assert "unknown_question" in spec.description

    def test_failed_dispatch_still_allows_future_repairs(
        self, repairer: AutoRepairer
    ) -> None:
        repairer._cooldown_minutes = 0

        for i in range(3):
            repairer.record_failure(make_failure(f"2024-01-01T12:00:0{i}"))

        failures = repairer._failure_logger.read_all()
        spec = repairer._generate_spec(failures)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Error"

        with patch("src.feedback.auto_repairer.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = MagicMock(return_value=mock_response)
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_client

            repairer._dispatch_repair_sync(spec, failures)

        repairer._last_repair_time = time.time() - 1
        repairer._failure_count = 5

        for i in range(3, 6):
            repairer.record_failure(make_failure(f"2024-01-01T12:01:0{i}"))

        with patch.object(repairer, "_dispatch_repair_sync"):
            assert repairer.maybe_repair() is True
