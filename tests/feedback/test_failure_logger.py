from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from src.feedback.failure_logger import ApplicationFailure, FailureLogger


@pytest.fixture
def temp_log_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "failures.jsonl"


@pytest.fixture
def logger(temp_log_path: Path) -> FailureLogger:
    return FailureLogger(log_path=temp_log_path)


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


class TestFailureTypeVariants:
    def test_unknown_question_details(self, logger: FailureLogger, temp_log_path: Path) -> None:
        failure = ApplicationFailure(
            timestamp="2024-01-01T12:00:00",
            job_url="https://example.com/job",
            job_title="Engineer",
            company="Corp",
            failure_type="unknown_question",
            details={
                "question_text": "What is your availability?",
                "field_type": "select",
                "field_id": "availability",
                "field_selector": "#availability",
                "page_url": "https://example.com/form",
            },
        )
        logger.log(failure)
        result = logger.read_all()
        assert len(result) == 1
        assert result[0].failure_type == "unknown_question"
        assert result[0].details["question_text"] == "What is your availability?"

    def test_stuck_loop_details(self, logger: FailureLogger) -> None:
        failure = ApplicationFailure(
            timestamp="2024-01-01T12:00:00",
            job_url="https://example.com/job",
            job_title="Engineer",
            company="Corp",
            failure_type="stuck_loop",
            details={
                "repeating_urls": ["url1", "url2"],
                "page_hash": "abc123",
                "iteration_count": 5,
                "last_actions": ["click", "scroll"],
            },
        )
        logger.log(failure)
        result = logger.read_all()
        assert result[0].details["iteration_count"] == 5

    def test_validation_error_details(self, logger: FailureLogger) -> None:
        failure = ApplicationFailure(
            timestamp="2024-01-01T12:00:00",
            job_url="https://example.com/job",
            job_title="Engineer",
            company="Corp",
            failure_type="validation_error",
            details={
                "error_messages": ["Invalid email format"],
                "field_selector": "#email",
                "field_value": "bad-email",
                "aria_invalid_fields": ["email"],
            },
        )
        logger.log(failure)
        result = logger.read_all()
        assert result[0].details["error_messages"] == ["Invalid email format"]

    def test_react_select_fail_details(self, logger: FailureLogger) -> None:
        failure = ApplicationFailure(
            timestamp="2024-01-01T12:00:00",
            job_url="https://example.com/job",
            job_title="Engineer",
            company="Corp",
            failure_type="react_select_fail",
            details={
                "selector": "#country-select",
                "attempted_value": "United States",
                "available_options": ["USA", "Canada", "UK"],
                "error": "Option not found",
            },
        )
        logger.log(failure)
        result = logger.read_all()
        assert result[0].details["available_options"] == ["USA", "Canada", "UK"]

    def test_timeout_details(self, logger: FailureLogger) -> None:
        failure = ApplicationFailure(
            timestamp="2024-01-01T12:00:00",
            job_url="https://example.com/job",
            job_title="Engineer",
            company="Corp",
            failure_type="timeout",
            details={
                "page_url": "https://example.com/slow-page",
                "last_action": "submit_form",
                "elapsed_seconds": 30.5,
            },
        )
        logger.log(failure)
        result = logger.read_all()
        assert result[0].details["elapsed_seconds"] == 30.5

    def test_crash_details(self, logger: FailureLogger) -> None:
        failure = ApplicationFailure(
            timestamp="2024-01-01T12:00:00",
            job_url="https://example.com/job",
            job_title="Engineer",
            company="Corp",
            failure_type="crash",
            details={
                "exception_type": "RuntimeError",
                "exception_message": "Something went wrong",
                "traceback": "Traceback (most recent call last)...",
            },
        )
        logger.log(failure)
        result = logger.read_all()
        assert result[0].details["exception_type"] == "RuntimeError"


class TestAppendOnlyJSONL:
    def test_log_appends_to_file(
        self, logger: FailureLogger, sample_failure: ApplicationFailure, temp_log_path: Path
    ) -> None:
        logger.log(sample_failure)
        logger.log(sample_failure)

        with open(temp_log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_each_line_is_valid_json(
        self, logger: FailureLogger, sample_failure: ApplicationFailure, temp_log_path: Path
    ) -> None:
        logger.log(sample_failure)
        logger.log(sample_failure)

        with open(temp_log_path, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                assert "timestamp" in data
                assert "failure_type" in data


class TestDirectoryCreation:
    def test_creates_data_directory_if_not_exists(
        self, logger: FailureLogger, sample_failure: ApplicationFailure, temp_log_path: Path
    ) -> None:
        assert not temp_log_path.parent.exists()
        logger.log(sample_failure)
        assert temp_log_path.parent.exists()
        assert temp_log_path.exists()


class TestThreadSafety:
    def test_concurrent_writes(self, logger: FailureLogger, temp_log_path: Path) -> None:
        failures: list[ApplicationFailure] = []
        for i in range(10):
            failures.append(
                ApplicationFailure(
                    timestamp=f"2024-01-01T12:00:{i:02d}",
                    job_url=f"https://example.com/job/{i}",
                    job_title="Engineer",
                    company="Corp",
                    failure_type="crash",
                    details={"exception_type": "Error", "exception_message": f"Error {i}", "traceback": "..."},
                )
            )

        threads = [threading.Thread(target=logger.log, args=(f,)) for f in failures]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        result = logger.read_all()
        assert len(result) == 10


class TestISOTimestamp:
    def test_timestamp_format_preserved(
        self, logger: FailureLogger, temp_log_path: Path
    ) -> None:
        iso_timestamp = "2024-03-15T14:30:00.123456"
        failure = ApplicationFailure(
            timestamp=iso_timestamp,
            job_url="https://example.com/job",
            job_title="Engineer",
            company="Corp",
            failure_type="crash",
            details={"exception_type": "Error", "exception_message": "msg", "traceback": "..."},
        )
        logger.log(failure)
        result = logger.read_all()
        assert result[0].timestamp == iso_timestamp


class TestReadAll:
    def test_read_all_returns_unaddressed_by_default(
        self, logger: FailureLogger, temp_log_path: Path
    ) -> None:
        failure1 = ApplicationFailure(
            timestamp="2024-01-01T12:00:00",
            job_url="https://example.com/job/1",
            job_title="Engineer",
            company="Corp",
            failure_type="crash",
            details={"exception_type": "Error", "exception_message": "msg", "traceback": "..."},
            addressed=False,
        )
        failure2 = ApplicationFailure(
            timestamp="2024-01-01T12:00:01",
            job_url="https://example.com/job/2",
            job_title="Engineer",
            company="Corp",
            failure_type="crash",
            details={"exception_type": "Error", "exception_message": "msg", "traceback": "..."},
            addressed=True,
        )
        logger.log(failure1)
        logger.log(failure2)

        result = logger.read_all()
        assert len(result) == 1
        assert result[0].timestamp == "2024-01-01T12:00:00"

    def test_read_all_includes_addressed_when_flag_set(
        self, logger: FailureLogger, temp_log_path: Path
    ) -> None:
        failure1 = ApplicationFailure(
            timestamp="2024-01-01T12:00:00",
            job_url="https://example.com/job/1",
            job_title="Engineer",
            company="Corp",
            failure_type="crash",
            details={"exception_type": "Error", "exception_message": "msg", "traceback": "..."},
            addressed=False,
        )
        failure2 = ApplicationFailure(
            timestamp="2024-01-01T12:00:01",
            job_url="https://example.com/job/2",
            job_title="Engineer",
            company="Corp",
            failure_type="crash",
            details={"exception_type": "Error", "exception_message": "msg", "traceback": "..."},
            addressed=True,
        )
        logger.log(failure1)
        logger.log(failure2)

        result = logger.read_all(include_addressed=True)
        assert len(result) == 2


class TestMarkAddressed:
    def test_mark_addressed_updates_failures(
        self, logger: FailureLogger, temp_log_path: Path
    ) -> None:
        failure1 = ApplicationFailure(
            timestamp="2024-01-01T12:00:00",
            job_url="https://example.com/job/1",
            job_title="Engineer",
            company="Corp",
            failure_type="crash",
            details={"exception_type": "Error", "exception_message": "msg", "traceback": "..."},
        )
        failure2 = ApplicationFailure(
            timestamp="2024-01-01T12:00:01",
            job_url="https://example.com/job/2",
            job_title="Engineer",
            company="Corp",
            failure_type="crash",
            details={"exception_type": "Error", "exception_message": "msg", "traceback": "..."},
        )
        logger.log(failure1)
        logger.log(failure2)

        logger.mark_addressed(["2024-01-01T12:00:00"])

        result = logger.read_all(include_addressed=True)
        assert len(result) == 2
        addressed = [f for f in result if f.addressed]
        unaddressed = [f for f in result if not f.addressed]
        assert len(addressed) == 1
        assert len(unaddressed) == 1
        assert addressed[0].timestamp == "2024-01-01T12:00:00"


class TestEdgeCases:
    def test_file_does_not_exist_returns_empty_list(
        self, logger: FailureLogger, temp_log_path: Path
    ) -> None:
        result = logger.read_all()
        assert result == []

    def test_malformed_line_skipped_with_warning(
        self, logger: FailureLogger, temp_log_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        temp_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_log_path, "w", encoding="utf-8") as f:
            f.write("not valid json\n")
            f.write(
                json.dumps(
                    {
                        "timestamp": "2024-01-01T12:00:00",
                        "job_url": "https://example.com/job",
                        "job_title": "Engineer",
                        "company": "Corp",
                        "failure_type": "crash",
                        "details": {"exception_type": "E", "exception_message": "m", "traceback": "t"},
                        "page_snapshot": None,
                        "addressed": False,
                    }
                )
                + "\n"
            )

        result = logger.read_all()
        assert len(result) == 1
        assert "Skipping malformed line" in caplog.text

    def test_non_serializable_objects_converted_to_str(
        self, logger: FailureLogger, temp_log_path: Path
    ) -> None:
        class CustomObject:
            def __str__(self) -> str:
                return "custom_object_repr"

        failure = ApplicationFailure(
            timestamp="2024-01-01T12:00:00",
            job_url="https://example.com/job",
            job_title="Engineer",
            company="Corp",
            failure_type="crash",
            details={
                "exception_type": "Error",
                "exception_message": "msg",
                "traceback": "...",
                "custom": CustomObject(),
            },
        )
        logger.log(failure)

        with open(temp_log_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read().strip())
        assert data["details"]["custom"] == "custom_object_repr"

    def test_mark_addressed_on_nonexistent_file(self, logger: FailureLogger) -> None:
        logger.mark_addressed(["2024-01-01T12:00:00"])

    def test_mark_addressed_preserves_malformed_lines(
        self, logger: FailureLogger, temp_log_path: Path
    ) -> None:
        temp_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_log_path, "w", encoding="utf-8") as f:
            f.write("malformed line\n")
            f.write(
                json.dumps(
                    {
                        "timestamp": "2024-01-01T12:00:00",
                        "job_url": "https://example.com/job",
                        "job_title": "Engineer",
                        "company": "Corp",
                        "failure_type": "crash",
                        "details": {"exception_type": "E", "exception_message": "m", "traceback": "t"},
                        "page_snapshot": None,
                        "addressed": False,
                    }
                )
                + "\n"
            )

        logger.mark_addressed(["2024-01-01T12:00:00"])

        with open(temp_log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert lines[0].strip() == "malformed line"
