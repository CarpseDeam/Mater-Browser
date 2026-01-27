"""Background worker for Playwright operations.

This module provides a thread-safe worker that owns its own browser connection
and ApplicationAgent, keeping all Playwright operations off the main GUI thread.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum, auto
from queue import Empty, Queue
from typing import TYPE_CHECKING, Callable, Optional

from src.agent.application import ApplicationAgent
from src.agent.models import ApplicationStatus
from src.automation.runner import ApplyRequest, ApplyResult
from src.browser.connection import BrowserConnection
from src.browser.tabs import TabManager

if TYPE_CHECKING:
    from src.core.config import Settings
    from src.profile.manager import Profile

logger = logging.getLogger(__name__)

QUEUE_POLL_TIMEOUT: float = 0.5
SHUTDOWN_TIMEOUT: float = 10.0


class WorkerCommand(Enum):
    """Commands that can be sent to the worker thread."""
    APPLY = auto()
    SHUTDOWN = auto()


@dataclass
class WorkerTask:
    """Task to be processed by the worker thread."""
    command: WorkerCommand
    request: Optional[ApplyRequest] = None


class WorkerState(Enum):
    """Current state of the worker thread."""
    IDLE = "idle"
    CONNECTING = "connecting"
    READY = "ready"
    PROCESSING = "processing"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    LOGIN_REQUIRED = "login_required"


@dataclass
class WorkerStatus:
    """Status update from worker to GUI."""
    state: WorkerState
    message: str = ""
    error: Optional[str] = None


class ApplyWorker:
    """Background worker that owns browser connection and processes apply requests.

    This worker runs in its own thread and owns:
    - Its own BrowserConnection (Playwright context)
    - Its own TabManager
    - Its own ApplicationAgent

    The GUI sends apply requests via the task queue and receives results
    via the result queue. Status updates are sent via the status callback.
    """

    def __init__(
        self,
        profile: Profile,
        settings: Settings,
        on_status: Optional[Callable[[WorkerStatus], None]] = None,
        on_result: Optional[Callable[[ApplyResult], None]] = None,
    ) -> None:
        """Initialize the worker.

        Args:
            profile: User profile for applications.
            settings: Application settings.
            on_status: Callback for status updates (called from worker thread).
            on_result: Callback for apply results (called from worker thread).
        """
        self._profile = profile
        self._settings = settings
        self._on_status = on_status
        self._on_result = on_result

        self._task_queue: Queue[WorkerTask] = Queue()
        self._thread: Optional[threading.Thread] = None
        self._state = WorkerState.IDLE
        self._stop_flag = threading.Event()

        self._connection: Optional[BrowserConnection] = None
        self._tabs: Optional[TabManager] = None
        self._agent: Optional[ApplicationAgent] = None

    @property
    def state(self) -> WorkerState:
        """Current worker state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Check if worker thread is active."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_ready(self) -> bool:
        """Check if worker is connected and ready to process requests."""
        return self._state == WorkerState.READY or self._state == WorkerState.PROCESSING

    def start(self) -> bool:
        """Start the worker thread.

        Returns:
            True if started successfully, False if already running.
        """
        if self.is_running:
            logger.warning("Worker already running")
            return False

        self._stop_flag.clear()
        self._state = WorkerState.IDLE
        self._thread = threading.Thread(target=self._run, daemon=True, name="ApplyWorker")
        self._thread.start()
        logger.info("ApplyWorker thread started")
        return True

    def stop(self) -> None:
        """Signal the worker to stop gracefully."""
        if not self.is_running:
            return

        logger.info("Stopping ApplyWorker...")
        self._stop_flag.set()
        self._task_queue.put(WorkerTask(command=WorkerCommand.SHUTDOWN))

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Wait for worker thread to stop.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            True if stopped, False if timeout expired.
        """
        if self._thread is None:
            return True

        self._thread.join(timeout=timeout or SHUTDOWN_TIMEOUT)
        return not self._thread.is_alive()

    def submit_apply(self, request: ApplyRequest) -> bool:
        """Submit an apply request to the worker.

        Args:
            request: The apply request to process.

        Returns:
            True if submitted, False if worker not ready.
        """
        if not self.is_ready:
            logger.warning("Cannot submit: worker not ready")
            return False

        self._task_queue.put(WorkerTask(command=WorkerCommand.APPLY, request=request))
        return True

    def _emit_status(self, state: WorkerState, message: str = "", error: Optional[str] = None) -> None:
        """Emit a status update to the callback."""
        self._state = state
        if self._on_status:
            try:
                self._on_status(WorkerStatus(state=state, message=message, error=error))
            except Exception as e:
                logger.error(f"Status callback error: {e}")

    def _emit_result(self, result: ApplyResult) -> None:
        """Emit an apply result to the callback."""
        if self._on_result:
            try:
                self._on_result(result)
            except Exception as e:
                logger.error(f"Result callback error: {e}")

    def _run(self) -> None:
        """Main worker loop running in background thread."""
        logger.info("ApplyWorker loop starting")

        try:
            if not self._connect():
                self._emit_status(WorkerState.ERROR, error="Failed to connect to browser")
                return

            self._emit_status(WorkerState.READY, message="Connected and ready")
            self._process_loop()

        except Exception as e:
            logger.exception(f"Worker error: {e}")
            self._emit_status(WorkerState.ERROR, error=str(e))

        finally:
            self._disconnect()
            self._emit_status(WorkerState.STOPPED, message="Worker stopped")
            logger.info("ApplyWorker loop stopped")

    def _connect(self) -> bool:
        """Connect to browser and initialize agent."""
        self._emit_status(WorkerState.CONNECTING, message="Connecting to browser...")

        self._connection = BrowserConnection(
            cdp_port=self._settings.browser.cdp_port,
            max_retries=3,
            retry_delay=1.0,
        )

        if not self._connection.connect():
            logger.error("Failed to connect to browser")
            return False

        try:
            self._tabs = TabManager(self._connection.browser)
            self._tabs.close_extras(keep=1)

            self._agent = ApplicationAgent(
                tab_manager=self._tabs,
                max_pages=15,
            )

            logger.info("ApplyWorker connected and agent initialized")
            return True

        except Exception as e:
            logger.exception(f"Failed to initialize agent: {e}")
            return False

    def _disconnect(self) -> None:
        """Disconnect from browser and clean up."""
        self._agent = None
        self._tabs = None

        if self._connection:
            try:
                self._connection.disconnect()
            except Exception as e:
                logger.debug(f"Disconnect error: {e}")
            self._connection = None

    def _process_loop(self) -> None:
        """Process tasks from the queue until shutdown."""
        while not self._stop_flag.is_set():
            try:
                task = self._task_queue.get(timeout=QUEUE_POLL_TIMEOUT)
            except Empty:
                continue

            if task.command == WorkerCommand.SHUTDOWN:
                logger.info("Received shutdown command")
                break

            if task.command == WorkerCommand.APPLY and task.request:
                self._process_apply(task.request)

    def _process_apply(self, request: ApplyRequest) -> None:
        """Process a single apply request."""
        job = request.job
        logger.info(f"Processing apply: {job.title} at {job.company}")

        self._emit_status(WorkerState.PROCESSING, message=f"Applying to {job.company}")

        if self._agent is None:
            result = ApplyResult(
                job=job,
                success=False,
                error="Agent not initialized",
            )
            self._emit_result(result)
            self._emit_status(WorkerState.READY)
            return

        try:
            app_result = self._agent.apply(job.url)
            success = app_result.status == ApplicationStatus.SUCCESS

            result = ApplyResult(
                job=job,
                success=success,
                error=None if success else app_result.message,
            )

            if app_result.status == ApplicationStatus.NEEDS_LOGIN:
                logger.warning(f"Login required: {app_result.message}")
                self._emit_status(
                    WorkerState.LOGIN_REQUIRED,
                    message=app_result.message,
                )

            logger.info(f"Apply result: {'success' if success else app_result.message}")

        except Exception as e:
            logger.exception(f"Apply error: {e}")
            result = ApplyResult(
                job=job,
                success=False,
                error=str(e),
            )

        self._emit_result(result)
        self._emit_status(WorkerState.READY)
