"""Automation runner for continuous job application loop.

This module orchestrates job searching and application in a background thread.
Playwright operations are marshaled to the main thread via request/response queues
to avoid greenlet threading errors.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Optional

from src.automation.search_generator import SearchGenerator
from src.queue.manager import JobQueue
from src.scraper.jobspy_client import JobSpyClient
from src.scraper.scorer import ACCOUNT_REQUIRED_DOMAINS, JobScorer

if TYPE_CHECKING:
    from queue import Queue

    from src.core.config import Settings
    from src.profile.manager import Profile
    from src.scraper.jobspy_client import JobListing

logger = logging.getLogger(__name__)

APPLY_DELAY_SECONDS: float = 2.0
CYCLE_COOLDOWN_SECONDS: float = 5.0
DEFAULT_SEARCH_LOCATION: str = "remote"
MAX_CONSECUTIVE_FAILURES: int = 5
FAILURE_COOLDOWN_SECONDS: float = 60.0
APPLY_TIMEOUT_SECONDS: float = 300.0

BLOCKED_URL_PATTERNS: list[str] = [
    # Payment
    "premium", "upgrade", "pricing", "subscribe",
    "checkout", "billing", "payment",
    # Account creation
    "register", "signup", "sign-up", "create-account",
    "createaccount", "registration", "newuser",
]


@dataclass
class ApplyRequest:
    """Request to apply to a job, sent from runner to main thread.

    Attributes:
        job: The job listing to apply to.
    """

    job: JobListing


@dataclass
class ApplyResult:
    """Result of apply attempt, sent from main thread to runner.

    Attributes:
        job: The job listing that was processed.
        success: Whether the application succeeded.
        error: Error message if application failed.
    """

    job: JobListing
    success: bool
    error: Optional[str] = None


class RunnerState(Enum):
    """State machine states for automation runner."""

    IDLE = "idle"
    SEARCHING = "searching"
    APPLYING = "applying"


@dataclass
class RunnerStats:
    """Statistics for the automation runner.

    Attributes:
        jobs_found: Total jobs discovered across all searches.
        jobs_applied: Total application attempts made.
        success_count: Successful applications.
        failed_count: Failed application attempts.
        current_search: Current search term being processed.
        current_job: Current job title being applied to.
    """

    jobs_found: int = 0
    jobs_applied: int = 0
    success_count: int = 0
    failed_count: int = 0
    current_search: str = ""
    current_job: str = ""


class AutomationRunner:
    """Orchestrates autonomous job searching and application.

    Composes SearchGenerator, JobSpyClient, JobScorer, and JobQueue into a
    continuous automation loop. Runs in a background thread with graceful
    stop support.

    Application requests are sent to the main thread via apply_queue, and
    results are received via result_queue. This avoids Playwright greenlet
    threading errors by keeping all browser operations on the main thread.

    Attributes:
        state: Current runner state (IDLE, SEARCHING, APPLYING).
        stats: Current statistics.
    """

    def __init__(
        self,
        profile: Profile,
        settings: Settings,
        apply_queue: Queue[ApplyRequest],
        result_queue: Queue[ApplyResult],
        on_progress: Callable[[str, dict], None] | None = None,
    ) -> None:
        """Initialize automation runner with dependencies.

        Args:
            profile: User profile for job matching and applications.
            settings: Application settings including Claude config.
            apply_queue: Queue for sending apply requests to main thread.
            result_queue: Queue for receiving apply results from main thread.
            on_progress: Optional callback for progress events.
        """
        self._profile = profile
        self._settings = settings
        self._apply_queue = apply_queue
        self._result_queue = result_queue
        self._on_progress = on_progress

        self._search_gen = SearchGenerator(profile)
        self._scraper = JobSpyClient()
        self._scorer = JobScorer(profile.model_dump())
        self._queue = JobQueue()

        self._state = RunnerState.IDLE
        self._stop_flag = threading.Event()
        self._thread: threading.Thread | None = None
        self._stats = RunnerStats()
        self._consecutive_failures: int = 0

    @property
    def state(self) -> RunnerState:
        """Return current runner state."""
        return self._state

    @property
    def stats(self) -> RunnerStats:
        """Return current statistics."""
        return self._stats

    @property
    def is_running(self) -> bool:
        """Return True if runner is active."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Start the automation loop in a background thread.

        Returns:
            True if started successfully, False if already running.
        """
        if self.is_running:
            logger.warning("Runner already active")
            return False

        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Automation runner started")
        return True

    def stop(self) -> None:
        """Signal the runner to stop gracefully.

        The current operation will complete before stopping.
        """
        if not self.is_running:
            return

        logger.info("Stop requested, finishing current operation...")
        self._stop_flag.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for runner to stop.

        Args:
            timeout: Maximum seconds to wait. None for indefinite.

        Returns:
            True if runner stopped, False if timeout expired.
        """
        if self._thread is None:
            return True

        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _emit(self, event_type: str, data: dict) -> None:
        """Emit a progress event to the callback.

        Args:
            event_type: Type of event (search_complete, apply_start, etc.).
            data: Event-specific data dictionary.
        """
        if self._on_progress:
            try:
                self._on_progress(event_type, data)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")

    def _run_loop(self) -> None:
        """Main automation loop running in background thread.

        Alternates between search cycles (finding jobs) and apply cycles
        (requesting applications via queue). Does not directly interact
        with Playwright - all browser operations are on main thread.
        """
        logger.info("Automation loop started")
        self._emit("started", {})

        try:
            while not self._stop_flag.is_set():
                self._run_search_cycle()

                if self._stop_flag.is_set():
                    break

                self._run_apply_cycle()

                if self._stop_flag.is_set():
                    break

                time.sleep(CYCLE_COOLDOWN_SECONDS)

        except Exception as e:
            logger.exception(f"Automation loop error: {e}")
            self._emit("error", {"message": str(e)})

        finally:
            self._state = RunnerState.IDLE
            self._emit("stopped", {"stats": self._stats_dict()})
            logger.info("Automation loop stopped")

    def _run_search_cycle(self) -> None:
        """Execute one search cycle."""
        self._state = RunnerState.SEARCHING
        term = self._search_gen.next()
        self._stats.current_search = term

        logger.info(f"Searching: {term}")
        self._emit("search_start", {"term": term})

        try:
            jobs = self._scraper.search(
                search_term=term,
                location=DEFAULT_SEARCH_LOCATION,
                remote_only=True,
            )
        except Exception as e:
            logger.error(f"Search failed: {e}")
            self._emit("search_failed", {"term": term, "error": str(e)})
            return

        scored = self._scorer.filter_and_score(jobs)
        added = self._queue.add_many(scored)

        self._stats.jobs_found += len(jobs)
        logger.info(f"Found {len(jobs)} jobs, {len(scored)} passed filter, {added} added to queue")

        self._emit(
            "search_complete",
            {
                "term": term,
                "found": len(jobs),
                "passed": len(scored),
                "added": added,
            },
        )

    def _run_apply_cycle(self) -> None:
        """Execute application cycle for queued jobs.

        Gets pending jobs from queue and sends apply requests to main thread.
        Waits for results and updates stats accordingly.
        """
        self._state = RunnerState.APPLYING
        logger.info("Starting apply cycle")

        while not self._stop_flag.is_set():
            job = self._queue.get_next()
            if job is None:
                logger.info("No more pending jobs in queue")
                break

            success = self._apply_to_job(job)

            if success:
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
                if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.warning(
                        f"Too many consecutive failures ({self._consecutive_failures}), "
                        f"pausing for {FAILURE_COOLDOWN_SECONDS}s..."
                    )
                    self._emit(
                        "paused",
                        {
                            "reason": "consecutive_failures",
                            "count": self._consecutive_failures,
                        },
                    )
                    time.sleep(FAILURE_COOLDOWN_SECONDS)
                    self._consecutive_failures = 0

            time.sleep(APPLY_DELAY_SECONDS)

        term = self._stats.current_search
        self._emit("cycle_complete", {"search_term": term})

    def _is_blocked_url(self, url: str) -> bool:
        """Check if URL contains blocked payment/upgrade patterns."""
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in BLOCKED_URL_PATTERNS)

    def _requires_account_creation(self, url: str) -> bool:
        """Check if URL is an external ATS requiring account."""
        url_lower = url.lower()
        return any(domain in url_lower for domain in ACCOUNT_REQUIRED_DOMAINS)

    def _apply_to_job(self, job: JobListing) -> bool:
        """Request application via queue and wait for result from main thread.

        Sends an ApplyRequest to the apply_queue and blocks waiting for
        an ApplyResult from the result_queue. This allows Playwright
        operations to happen on the main thread.

        Args:
            job: Job listing to apply to.

        Returns:
            True if application succeeded, False otherwise.
        """
        if self._is_blocked_url(job.url):
            reason = "Blocked URL pattern detected - potential payment page"
            logger.warning(f"BLOCKING {job.url}: {reason}")
            self._queue.mark_skipped(job.url, reason)
            return True

        if self._requires_account_creation(job.url):
            logger.info(f"Skipping external ATS (requires account): {job.url}")
            self._queue.mark_skipped(job.url, "External ATS requires account")
            return True

        if not self._scorer.passes_filter(job):
            reason = f"Failed re-validation: {self._scorer.get_exclusion_reason(job)}"
            logger.info(f"Skipping {job.title} at {job.company}: {reason}")
            self._queue.mark_skipped(job.url, reason)
            return True

        self._stats.current_job = f"{job.title} at {job.company}"
        logger.info(f"Requesting apply to: {self._stats.current_job}")

        self._emit(
            "apply_start",
            {
                "job": {
                    "title": job.title,
                    "company": job.company,
                    "url": job.url,
                }
            },
        )

        request = ApplyRequest(job=job)
        logger.debug(f"Putting ApplyRequest in queue for {job.url}")
        self._apply_queue.put(request)

        try:
            logger.debug(f"Waiting for ApplyResult (timeout={APPLY_TIMEOUT_SECONDS}s)")
            result = self._result_queue.get(timeout=APPLY_TIMEOUT_SECONDS)
        except queue.Empty:
            logger.error(
                f"Apply timeout after {APPLY_TIMEOUT_SECONDS}s - no response from main thread"
            )
            self._queue.mark_failed(job.url, "Apply timeout - no response from main thread")
            self._stats.jobs_applied += 1
            self._stats.failed_count += 1
            self._emit(
                "apply_failed",
                {
                    "job": {"title": job.title, "company": job.company, "url": job.url},
                    "error": "Apply timeout - no response from main thread",
                },
            )
            return False

        self._stats.jobs_applied += 1

        if result.success:
            self._queue.mark_applied(job.url)
            self._stats.success_count += 1
            logger.info(f"Successfully applied to {job.company}")
            self._emit(
                "apply_complete",
                {
                    "job": {"title": job.title, "company": job.company, "url": job.url},
                    "result": {"status": "success", "message": "Application submitted"},
                },
            )
            return True

        error_msg = result.error or "Unknown error"
        self._queue.mark_failed(job.url, error_msg)
        self._stats.failed_count += 1
        logger.warning(f"Failed to apply to {job.company}: {error_msg}")
        self._emit(
            "apply_failed",
            {
                "job": {"title": job.title, "company": job.company, "url": job.url},
                "error": error_msg,
            },
        )
        return False

    def _stats_dict(self) -> dict:
        """Convert stats to dictionary."""
        return {
            "jobs_found": self._stats.jobs_found,
            "jobs_applied": self._stats.jobs_applied,
            "success_count": self._stats.success_count,
            "failed_count": self._stats.failed_count,
        }
