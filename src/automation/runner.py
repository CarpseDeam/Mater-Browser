"""Automation runner for continuous job application loop."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable

from src.agent.application import ApplicationAgent, ApplicationStatus
from src.automation.search_generator import SearchGenerator
from src.browser.tabs import TabManager
from src.queue.manager import JobQueue
from src.scraper.jobspy_client import JobSpyClient
from src.scraper.scorer import JobScorer

if TYPE_CHECKING:
    from src.browser.connection import BrowserConnection
    from src.core.config import Settings
    from src.profile.manager import Profile
    from src.scraper.jobspy_client import JobListing

logger = logging.getLogger(__name__)

APPLY_DELAY_SECONDS: float = 2.0
CYCLE_COOLDOWN_SECONDS: float = 5.0
DEFAULT_SEARCH_LOCATION: str = "remote"
MAX_CONSECUTIVE_FAILURES: int = 5
FAILURE_COOLDOWN_SECONDS: float = 60.0


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

    Composes SearchGenerator, JobSpyClient, JobScorer, JobQueue, and
    ApplicationAgent into a continuous automation loop. Runs in a
    background thread with graceful stop support.

    Attributes:
        state: Current runner state (IDLE, SEARCHING, APPLYING).
        stats: Current statistics.
    """

    def __init__(
        self,
        connection: BrowserConnection,
        profile: Profile,
        settings: Settings,
        on_progress: Callable[[str, dict], None] | None = None,
    ) -> None:
        """Initialize automation runner with dependencies.

        Args:
            connection: Browser connection for CDP communication.
            profile: User profile for job matching and applications.
            settings: Application settings including Claude config.
            on_progress: Optional callback for progress events.
        """
        self._connection = connection
        self._profile = profile
        self._settings = settings
        self._on_progress = on_progress

        self._search_gen = SearchGenerator(profile)
        self._scraper = JobSpyClient()
        self._scorer = JobScorer(profile.model_dump())
        self._queue = JobQueue()

        self._state = RunnerState.IDLE
        self._stop_flag = threading.Event()
        self._thread: threading.Thread | None = None
        self._stats = RunnerStats()
        self._agent: ApplicationAgent | None = None

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
        """Main automation loop running in background thread."""
        logger.info("Automation loop started")
        self._emit("started", {})

        try:
            self._init_agent()

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

    def _init_agent(self) -> None:
        """Initialize the application agent."""
        tab_manager = TabManager(self._connection.browser)
        self._agent = ApplicationAgent(
            tab_manager=tab_manager,
            profile=self._profile.model_dump(),
            resume_path=self._profile.resume_path or None,
            claude_model=self._settings.claude.model,
        )

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
        """Execute application cycle for queued jobs."""
        self._state = RunnerState.APPLYING
        consecutive_failures = 0

        while not self._stop_flag.is_set():
            job = self._queue.get_next()
            if job is None:
                logger.info("No more pending jobs in queue")
                break

            success = self._apply_to_job(job)

            if success:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.warning(
                        f"Too many consecutive failures ({consecutive_failures}), pausing..."
                    )
                    self._emit(
                        "paused",
                        {"reason": "consecutive_failures", "count": consecutive_failures},
                    )
                    time.sleep(FAILURE_COOLDOWN_SECONDS)
                    consecutive_failures = 0

            time.sleep(APPLY_DELAY_SECONDS)

        term = self._stats.current_search
        self._emit("cycle_complete", {"search_term": term})

    def _apply_to_job(self, job: JobListing) -> bool:
        """Apply to a single job.

        Args:
            job: Job listing to apply to.

        Returns:
            True if application succeeded, False otherwise.
        """
        if self._agent is None:
            logger.error("Agent not initialized")
            return False

        self._stats.current_job = f"{job.title} at {job.company}"
        logger.info(f"Applying to: {self._stats.current_job}")

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

        try:
            result = self._agent.apply(job.url)
        except Exception as e:
            logger.error(f"Application error: {e}")
            self._queue.mark_failed(job.url, str(e))
            self._stats.jobs_applied += 1
            self._stats.failed_count += 1
            self._emit(
                "apply_failed",
                {
                    "job": {"title": job.title, "company": job.company, "url": job.url},
                    "error": str(e),
                },
            )
            return False

        self._stats.jobs_applied += 1

        if result.status == ApplicationStatus.SUCCESS:
            self._queue.mark_applied(job.url)
            self._stats.success_count += 1
            logger.info(f"Successfully applied to {job.company}")
            self._emit(
                "apply_complete",
                {
                    "job": {"title": job.title, "company": job.company, "url": job.url},
                    "result": {"status": result.status.value, "message": result.message},
                },
            )
            return True

        self._queue.mark_failed(job.url, result.message)
        self._stats.failed_count += 1
        logger.warning(f"Failed to apply to {job.company}: {result.message}")
        self._emit(
            "apply_failed",
            {
                "job": {"title": job.title, "company": job.company, "url": job.url},
                "result": {"status": result.status.value, "message": result.message},
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
