from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

from src.feedback.auto_repairer import AutoRepairer
from src.feedback.failure_logger import ApplicationFailure


@pytest.fixture
def repairer() -> AutoRepairer:
    with patch("src.feedback.auto_repairer.FailureLogger"):
        return AutoRepairer(threshold=5)


@pytest.fixture
def sample_failure() -> ApplicationFailure:
    return ApplicationFailure(
        timestamp="2024-01-01T00:00:00",
        job_url="https://example.com/job/123",
        job_title="Software Engineer",
        company="Example Corp",
        failure_type="unknown_question",
        details={"question": "test question"},
    )


def test_counter_lock_initialized(repairer: AutoRepairer) -> None:
    assert hasattr(repairer, "_counter_lock")
    assert isinstance(repairer._counter_lock, type(threading.Lock()))


def test_record_failure_increments_under_lock(
    repairer: AutoRepairer, sample_failure: ApplicationFailure
) -> None:
    repairer.record_failure(sample_failure)
    assert repairer._failure_count == 1


def test_maybe_repair_checks_threshold_under_lock(repairer: AutoRepairer) -> None:
    repairer._failure_count = 3
    result = repairer.maybe_repair()
    assert result is False


def test_concurrent_record_failures(sample_failure: ApplicationFailure) -> None:
    with patch("src.feedback.auto_repairer.FailureLogger"):
        repairer = AutoRepairer(threshold=10000)

    num_threads = 10
    increments_per_thread = 100
    threads: list[threading.Thread] = []

    def record_failures() -> None:
        for _ in range(increments_per_thread):
            repairer.record_failure(sample_failure)

    for _ in range(num_threads):
        t = threading.Thread(target=record_failures)
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    expected_count = num_threads * increments_per_thread
    assert repairer._failure_count == expected_count
