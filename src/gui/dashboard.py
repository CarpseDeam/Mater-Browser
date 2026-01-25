"""Simplified autonomous dashboard for job application automation."""

from __future__ import annotations

import logging
import subprocess
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from tkinter import scrolledtext, ttk
from typing import TYPE_CHECKING

from src.automation.runner import AutomationRunner, RunnerState
from src.browser.connection import BrowserConnection
from src.core.config import Settings
from src.core.logging import setup_logging
from src.profile.manager import load_profile

if TYPE_CHECKING:
    from src.profile.manager import Profile

logger = logging.getLogger(__name__)

WINDOW_TITLE: str = "Mater-Browser - Autonomous Job Applicant"
WINDOW_GEOMETRY: str = "700x550"
WINDOW_MIN_SIZE: tuple[int, int] = (600, 450)
MESSAGE_POLL_MS: int = 100
MAX_LOG_LINES: int = 500

BG_DARK: str = "#1e1e1e"
BG_MEDIUM: str = "#2d2d2d"
BG_LIGHT: str = "#3c3c3c"
FG_TEXT: str = "#e0e0e0"
FG_DIM: str = "#a0a0a0"
ACCENT: str = "#4fc3f7"
SUCCESS_COLOR: str = "#81c784"
ERROR_COLOR: str = "#e57373"


@dataclass
class DashboardStats:
    """Dashboard statistics tracker.

    Attributes:
        jobs_found: Total jobs discovered.
        jobs_applied: Total application attempts.
        success_count: Successful applications.
        failed_count: Failed applications.
    """

    jobs_found: int = 0
    jobs_applied: int = 0
    success_count: int = 0
    failed_count: int = 0


class LogHandler(logging.Handler):
    """Custom handler to send logs to GUI queue.

    Attributes:
        queue: Queue for thread-safe message passing.
    """

    def __init__(self, queue: Queue) -> None:
        """Initialize log handler with message queue.

        Args:
            queue: Queue for sending log messages.
        """
        super().__init__()
        self.queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the queue.

        Args:
            record: Log record to emit.
        """
        msg = self.format(record)
        self.queue.put(("log", msg))


class DashboardApp:
    """Simplified autonomous job application dashboard.

    Single-button interface for fully autonomous job searching and application.
    Displays real-time statistics and activity log.

    Attributes:
        root: Tkinter root window.
        connection: Browser connection instance.
        runner: Automation runner instance.
        stats: Current dashboard statistics.
    """

    def __init__(self) -> None:
        """Initialize the dashboard application."""
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_GEOMETRY)
        self.root.minsize(*WINDOW_MIN_SIZE)

        self.connection: BrowserConnection | None = None
        self.runner: AutomationRunner | None = None
        self.message_queue: Queue = Queue()
        self.stats = DashboardStats()

        self.settings = Settings.from_yaml(Path("config/settings.yaml"))
        self.profile = load_profile(Path("config/profile.yaml"))

        setup_logging("INFO")
        log_handler = LogHandler(self.message_queue)
        log_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(message)s", "%H:%M:%S")
        )
        logging.getLogger().addHandler(log_handler)

        self._build_ui()
        self._process_messages()

    def _build_ui(self) -> None:
        """Build the dashboard user interface."""
        self.root.configure(bg=BG_DARK)

        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background=BG_DARK)
        style.configure("TLabel", background=BG_DARK, foreground=FG_TEXT)

        style.configure(
            "TButton",
            background=BG_LIGHT,
            foreground=FG_TEXT,
            borderwidth=1,
            focuscolor=BG_LIGHT,
            padding=(10, 5),
        )
        style.map(
            "TButton",
            background=[("active", BG_MEDIUM), ("disabled", BG_DARK)],
            foreground=[("disabled", FG_DIM)],
        )

        style.configure(
            "Start.TButton",
            background=SUCCESS_COLOR,
            foreground=BG_DARK,
            font=("Segoe UI", 14, "bold"),
            padding=(30, 15),
        )
        style.map(
            "Start.TButton",
            background=[("active", "#66bb6a"), ("disabled", BG_DARK)],
            foreground=[("disabled", FG_DIM)],
        )

        style.configure(
            "Stop.TButton",
            background=ERROR_COLOR,
            foreground=BG_DARK,
            font=("Segoe UI", 14, "bold"),
            padding=(30, 15),
        )
        style.map(
            "Stop.TButton",
            background=[("active", "#ef5350")],
        )

        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        self._build_connection_section(main)
        self._build_control_section(main)
        self._build_stats_section(main)
        self._build_status_section(main)
        self._build_log_section(main)

    def _build_connection_section(self, parent: ttk.Frame) -> None:
        """Build the connection status section.

        Args:
            parent: Parent frame.
        """
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(0, 15))

        self.status_label = ttk.Label(frame, text="⚪ Not Connected", font=("Segoe UI", 10))
        self.status_label.pack(side=tk.LEFT)

        self.start_chrome_btn = ttk.Button(
            frame, text="Start Chrome", command=self._start_chrome
        )
        self.start_chrome_btn.pack(side=tk.RIGHT, padx=(5, 0))

        self.connect_btn = ttk.Button(
            frame, text="Connect to Chrome", command=self._connect_browser
        )
        self.connect_btn.pack(side=tk.RIGHT)

    def _build_control_section(self, parent: ttk.Frame) -> None:
        """Build the main control button section.

        Args:
            parent: Parent frame.
        """
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=20)

        self.control_btn = ttk.Button(
            frame,
            text="▶  START",
            style="Start.TButton",
            command=self._toggle_automation,
            state=tk.DISABLED,
        )
        self.control_btn.pack(expand=True)

    def _build_stats_section(self, parent: ttk.Frame) -> None:
        """Build the statistics display section.

        Args:
            parent: Parent frame.
        """
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(0, 15))

        stats_container = ttk.Frame(frame)
        stats_container.pack(expand=True)

        self.stat_labels: dict[str, ttk.Label] = {}
        stat_items = [
            ("found", "Jobs Found"),
            ("applied", "Applied"),
            ("success", "Success"),
            ("failed", "Failed"),
        ]

        for i, (key, label) in enumerate(stat_items):
            col_frame = ttk.Frame(stats_container)
            col_frame.grid(row=0, column=i, padx=20)

            value_label = ttk.Label(
                col_frame, text="0", font=("Segoe UI", 24, "bold"), foreground=ACCENT
            )
            value_label.pack()

            name_label = ttk.Label(col_frame, text=label, font=("Segoe UI", 9), foreground=FG_DIM)
            name_label.pack()

            self.stat_labels[key] = value_label

    def _build_status_section(self, parent: ttk.Frame) -> None:
        """Build the current activity status section.

        Args:
            parent: Parent frame.
        """
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(0, 10))

        self.activity_label = ttk.Label(
            frame, text="Ready to start", font=("Segoe UI", 10), foreground=FG_DIM
        )
        self.activity_label.pack()

    def _build_log_section(self, parent: ttk.Frame) -> None:
        """Build the activity log section.

        Args:
            parent: Parent frame.
        """
        log_label = ttk.Label(parent, text="Activity Log", font=("Segoe UI", 9), foreground=FG_DIM)
        log_label.pack(anchor=tk.W)

        self.log_text = scrolledtext.ScrolledText(
            parent,
            wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED,
            bg=BG_MEDIUM,
            fg=FG_TEXT,
            insertbackground=FG_TEXT,
            selectbackground=ACCENT,
            selectforeground=BG_DARK,
            relief=tk.FLAT,
            borderwidth=0,
            padx=10,
            pady=10,
            height=12,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _log(self, message: str) -> None:
        """Add message to activity log.

        Args:
            message: Message to log.
        """
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")

        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > MAX_LOG_LINES:
            self.log_text.delete("1.0", f"{line_count - MAX_LOG_LINES}.0")

        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _update_connection_status(self, connected: bool) -> None:
        """Update connection status display.

        Args:
            connected: Whether browser is connected.
        """
        if connected:
            self.status_label.config(text="🟢 Connected")
            self.connect_btn.config(text="Disconnect")
            self.control_btn.config(state=tk.NORMAL)
        else:
            self.status_label.config(text="⚪ Not Connected")
            self.connect_btn.config(text="Connect to Chrome")
            self.control_btn.config(state=tk.DISABLED)

    def _update_stats_display(self) -> None:
        """Update statistics display from current stats."""
        self.stat_labels["found"].config(text=str(self.stats.jobs_found))
        self.stat_labels["applied"].config(text=str(self.stats.jobs_applied))
        self.stat_labels["success"].config(text=str(self.stats.success_count))
        self.stat_labels["failed"].config(text=str(self.stats.failed_count))

    def _start_chrome(self) -> None:
        """Start Chrome with debugging port."""
        script = Path("scripts/start_chrome.bat")
        if not script.exists():
            self._log("Error: scripts/start_chrome.bat not found")
            return

        subprocess.Popen(["cmd", "/c", str(script)], shell=True)
        self._log("Starting Chrome... Wait a few seconds then click Connect.")

    def _connect_browser(self) -> None:
        """Connect or disconnect from browser."""
        if self.connection and self.connection.is_connected:
            if self.runner and self.runner.is_running:
                self._log("Stop automation before disconnecting")
                return

            self.connection.disconnect()
            self.connection = None
            self._update_connection_status(False)
            self._log("Disconnected from Chrome")
            return

        self._log("Connecting to Chrome...")

        self.connection = BrowserConnection(
            cdp_port=self.settings.browser.cdp_port,
            max_retries=3,
            retry_delay=1.0,
        )

        if self.connection.connect():
            self._update_connection_status(True)
            self._log("Connected to Chrome!")
        else:
            self._log(
                "Failed to connect. Make sure Chrome is running with --remote-debugging-port"
            )
            self.connection = None

    def _toggle_automation(self) -> None:
        """Start or stop the automation runner."""
        if self.runner and self.runner.is_running:
            self._stop_automation()
        else:
            self._start_automation()

    def _start_automation(self) -> None:
        """Start the automation runner."""
        if not self.connection or not self.connection.is_connected:
            self._log("Connect to Chrome first")
            return

        self.runner = AutomationRunner(
            connection=self.connection,
            profile=self.profile,
            settings=self.settings,
            on_progress=self._on_runner_progress,
        )

        if self.runner.start():
            self.control_btn.config(text="⏹  STOP", style="Stop.TButton")
            self.connect_btn.config(state=tk.DISABLED)
            self.activity_label.config(text="Starting automation...", foreground=ACCENT)
            self._log("Automation started")

    def _stop_automation(self) -> None:
        """Stop the automation runner gracefully."""
        if not self.runner:
            return

        self.runner.stop()
        self.control_btn.config(state=tk.DISABLED)
        self.activity_label.config(text="Stopping... finishing current operation", foreground=FG_DIM)
        self._log("Stop requested, finishing current operation...")

    def _on_runner_progress(self, event: str, data: dict) -> None:
        """Handle progress events from automation runner.

        Args:
            event: Event type string.
            data: Event data dictionary.
        """
        self.message_queue.put((event, data))

    def _process_messages(self) -> None:
        """Process messages from worker thread."""
        try:
            while True:
                msg_type, data = self.message_queue.get_nowait()
                self._handle_message(msg_type, data)
        except Empty:
            pass

        self.root.after(MESSAGE_POLL_MS, self._process_messages)

    def _handle_message(self, msg_type: str, data) -> None:
        """Handle a single message from the queue.

        Args:
            msg_type: Type of message.
            data: Message data.
        """
        if msg_type == "log":
            self._log(data)

        elif msg_type == "started":
            self.activity_label.config(text="Automation running", foreground=ACCENT)

        elif msg_type == "stopped":
            self._on_automation_stopped(data)

        elif msg_type == "search_start":
            term = data.get("term", "")
            self.activity_label.config(text=f"Searching: {term}", foreground=ACCENT)
            self._log(f"Searching for: {term}")

        elif msg_type == "search_complete":
            self._on_search_complete(data)

        elif msg_type == "search_failed":
            term = data.get("term", "")
            error = data.get("error", "Unknown error")
            self._log(f"Search failed for '{term}': {error}")

        elif msg_type == "apply_start":
            job = data.get("job", {})
            title = job.get("title", "Unknown")
            company = job.get("company", "Unknown")
            self.activity_label.config(text=f"Applying: {title} at {company}", foreground=ACCENT)
            self._log(f"Applying to: {title} at {company}")

        elif msg_type == "apply_complete":
            self._on_apply_complete(data)

        elif msg_type == "apply_failed":
            self._on_apply_failed(data)

        elif msg_type == "cycle_complete":
            term = data.get("search_term", "")
            self._log(f"Cycle complete for: {term}")

        elif msg_type == "error":
            error = data.get("message", "Unknown error")
            self._log(f"ERROR: {error}")
            self.activity_label.config(text=f"Error: {error}", foreground=ERROR_COLOR)

    def _on_automation_stopped(self, data: dict) -> None:
        """Handle automation stopped event.

        Args:
            data: Event data with final stats.
        """
        self.control_btn.config(text="▶  START", style="Start.TButton", state=tk.NORMAL)
        self.connect_btn.config(state=tk.NORMAL)
        self.activity_label.config(text="Ready to start", foreground=FG_DIM)
        self._log("Automation stopped")

        stats = data.get("stats", {})
        self._log(
            f"Session summary: Found {stats.get('jobs_found', 0)}, "
            f"Applied {stats.get('jobs_applied', 0)}, "
            f"Success {stats.get('success_count', 0)}, "
            f"Failed {stats.get('failed_count', 0)}"
        )

    def _on_search_complete(self, data: dict) -> None:
        """Handle search complete event.

        Args:
            data: Search result data.
        """
        term = data.get("term", "")
        found = data.get("found", 0)
        passed = data.get("passed", 0)
        added = data.get("added", 0)

        self.stats.jobs_found += found
        self._update_stats_display()

        self._log(f"Found {found} jobs for '{term}', {passed} passed filter, {added} added to queue")

    def _on_apply_complete(self, data: dict) -> None:
        """Handle successful application event.

        Args:
            data: Application result data.
        """
        job = data.get("job", {})
        company = job.get("company", "Unknown")

        self.stats.jobs_applied += 1
        self.stats.success_count += 1
        self._update_stats_display()

        self._log(f"✓ Successfully applied to {company}")

    def _on_apply_failed(self, data: dict) -> None:
        """Handle failed application event.

        Args:
            data: Application failure data.
        """
        job = data.get("job", {})
        company = job.get("company", "Unknown")
        result = data.get("result", {})
        error = data.get("error", result.get("message", "Unknown error"))

        self.stats.jobs_applied += 1
        self.stats.failed_count += 1
        self._update_stats_display()

        self._log(f"✗ Failed to apply to {company}: {error}")

    def run(self) -> None:
        """Run the dashboard application."""
        self._log("Mater-Browser Dashboard started")
        self._log(f"Profile: {self.profile.first_name} {self.profile.last_name}")
        self._log(f"Title: {self.profile.current_title}")
        self._log("Click 'Start Chrome' then 'Connect to Chrome' to begin")

        self.root.mainloop()

        if self.runner and self.runner.is_running:
            self.runner.stop()
            self.runner.wait(timeout=10.0)

        if self.connection:
            self.connection.disconnect()
