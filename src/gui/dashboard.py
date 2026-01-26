"""Simplified autonomous dashboard for job application automation.

This module provides a single-button GUI for controlling the automation loop.
The dashboard owns the ApplicationAgent and processes apply requests on the
main thread to avoid Playwright greenlet threading errors.
"""

from __future__ import annotations

import logging
import subprocess
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from tkinter import scrolledtext, ttk
from typing import TYPE_CHECKING, Optional

from src.agent.application import ApplicationAgent, ApplicationStatus
from src.automation.runner import ApplyRequest, ApplyResult, AutomationRunner
from src.browser.connection import BrowserConnection
from src.browser.tabs import TabManager
from src.core.config import Settings
from src.core.logging import setup_logging
from src.profile.manager import load_profile

if TYPE_CHECKING:
    from src.profile.manager import Profile

logger = logging.getLogger(__name__)

WINDOW_TITLE: str = "Mater-Browser - Autonomous Job Applicant"
WINDOW_GEOMETRY: str = "800x700"
WINDOW_MIN_SIZE: tuple[int, int] = (700, 550)
MESSAGE_POLL_MS: int = 100
APPLY_QUEUE_POLL_MS: int = 100
MAX_LOG_LINES: int = 500
MAX_HISTORY_ENTRIES: int = 20

BG_DARK: str = "#1e1e1e"
BG_MEDIUM: str = "#2d2d2d"
BG_LIGHT: str = "#3c3c3c"
FG_TEXT: str = "#e0e0e0"
FG_DIM: str = "#808080"
ACCENT: str = "#4fc3f7"
SUCCESS_COLOR: str = "#81c784"
ERROR_COLOR: str = "#e57373"
WARNING_COLOR: str = "#ffb74d"


class StatusState:
    IDLE = "Idle"
    SEARCHING = "Searching..."
    NAVIGATING = "Navigating to job..."
    FILLING_FORM = "Filling form..."
    SUBMITTING = "Submitting..."
    COMPLETE = "Complete"
    ERROR = "Error"


@dataclass
class HistoryEntry:
    job_title: str
    company: str
    status: str  # "success", "failed", "in_progress"
    timestamp: float
    error_reason: Optional[str] = None


@dataclass
class DashboardStats:
    jobs_found: int = 0
    jobs_applied: int = 0
    success_count: int = 0
    failed_count: int = 0
    queue_pending: int = 0


@dataclass
class DashboardState:
    status: str = StatusState.IDLE
    current_job: str = ""
    current_search: str = ""
    form_progress: str = ""
    session_start: Optional[float] = None
    history: list[HistoryEntry] = field(default_factory=list)


class LogHandler(logging.Handler):
    def __init__(self, queue: Queue) -> None:
        super().__init__()
        self.queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.queue.put(("log", msg))


class DashboardApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_GEOMETRY)
        self.root.minsize(*WINDOW_MIN_SIZE)

        self.connection: Optional[BrowserConnection] = None
        self.runner: Optional[AutomationRunner] = None
        self.message_queue: Queue = Queue()
        self.stats = DashboardStats()
        self.state = DashboardState()

        self._apply_queue: Queue[ApplyRequest] = Queue()
        self._result_queue: Queue[ApplyResult] = Queue()
        self._agent: Optional[ApplicationAgent] = None
        self._log_expanded = False

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
        self._update_session_time()

    def _build_ui(self) -> None:
        self.root.configure(bg=BG_DARK)
        self._configure_styles()

        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        self._build_connection_section(main)
        self._build_control_section(main)
        self._build_status_panel(main)
        self._build_stats_bar(main)
        self._build_history_panel(main)
        self._build_log_panel(main)

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background=BG_DARK)
        style.configure("TLabel", background=BG_DARK, foreground=FG_TEXT)
        style.configure("Dim.TLabel", background=BG_DARK, foreground=FG_DIM)

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
        style.map("Stop.TButton", background=[("active", "#ef5350")])

        style.configure(
            "StatusPanel.TFrame",
            background=BG_MEDIUM,
        )

        style.configure(
            "Status.TLabel",
            background=BG_MEDIUM,
            foreground=ACCENT,
            font=("Segoe UI", 18, "bold"),
        )

        style.configure(
            "StatusInfo.TLabel",
            background=BG_MEDIUM,
            foreground=FG_TEXT,
            font=("Segoe UI", 11),
        )

        style.configure(
            "StatusDim.TLabel",
            background=BG_MEDIUM,
            foreground=FG_DIM,
            font=("Segoe UI", 10),
        )

        style.configure(
            "StatsBar.TFrame",
            background=BG_LIGHT,
        )

        style.configure(
            "StatValue.TLabel",
            background=BG_LIGHT,
            foreground=FG_TEXT,
            font=("Segoe UI", 11, "bold"),
        )

        style.configure(
            "StatLabel.TLabel",
            background=BG_LIGHT,
            foreground=FG_DIM,
            font=("Segoe UI", 9),
        )

        style.configure(
            "Treeview",
            background=BG_MEDIUM,
            foreground=FG_TEXT,
            fieldbackground=BG_MEDIUM,
            font=("Segoe UI", 10),
            rowheight=28,
        )
        style.configure(
            "Treeview.Heading",
            background=BG_LIGHT,
            foreground=FG_TEXT,
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", BG_LIGHT)],
            foreground=[("selected", FG_TEXT)],
        )

        style.configure(
            "Toggle.TButton",
            background=BG_MEDIUM,
            foreground=FG_DIM,
            font=("Segoe UI", 9),
            padding=(8, 3),
        )
        style.map(
            "Toggle.TButton",
            background=[("active", BG_LIGHT)],
        )

    def _build_connection_section(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(0, 10))

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
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=10)

        self.control_btn = ttk.Button(
            frame,
            text="▶  START",
            style="Start.TButton",
            command=self._toggle_automation,
            state=tk.DISABLED,
        )
        self.control_btn.pack(expand=True)

    def _build_status_panel(self, parent: ttk.Frame) -> None:
        frame = tk.Frame(parent, bg=BG_MEDIUM, padx=20, pady=15)
        frame.pack(fill=tk.X, pady=(0, 10))

        self.status_text = ttk.Label(
            frame, text=StatusState.IDLE, style="Status.TLabel"
        )
        self.status_text.pack(anchor=tk.W)

        info_frame = ttk.Frame(frame, style="StatusPanel.TFrame")
        info_frame.pack(fill=tk.X, pady=(8, 0))

        job_row = ttk.Frame(info_frame, style="StatusPanel.TFrame")
        job_row.pack(fill=tk.X, pady=2)
        ttk.Label(job_row, text="Current Job:", style="StatusDim.TLabel").pack(side=tk.LEFT)
        self.current_job_label = ttk.Label(job_row, text="—", style="StatusInfo.TLabel")
        self.current_job_label.pack(side=tk.LEFT, padx=(8, 0))

        search_row = ttk.Frame(info_frame, style="StatusPanel.TFrame")
        search_row.pack(fill=tk.X, pady=2)
        ttk.Label(search_row, text="Search Term:", style="StatusDim.TLabel").pack(side=tk.LEFT)
        self.current_search_label = ttk.Label(search_row, text="—", style="StatusInfo.TLabel")
        self.current_search_label.pack(side=tk.LEFT, padx=(8, 0))

    def _build_stats_bar(self, parent: ttk.Frame) -> None:
        frame = tk.Frame(parent, bg=BG_LIGHT, padx=15, pady=10)
        frame.pack(fill=tk.X, pady=(0, 10))

        stats_data = [
            ("queue", "Queue:", "0 pending"),
            ("processed", "Processed:", "0 (0 ✓ 0 ✗)"),
            ("session", "Session:", "0m 0s"),
        ]

        for i, (key, label, initial) in enumerate(stats_data):
            container = tk.Frame(frame, bg=BG_LIGHT)
            container.pack(side=tk.LEFT, padx=(0 if i == 0 else 20, 0))

            ttk.Label(container, text=label, style="StatLabel.TLabel").pack(side=tk.LEFT)
            value_label = ttk.Label(container, text=initial, style="StatValue.TLabel")
            value_label.pack(side=tk.LEFT, padx=(5, 0))

            if key == "queue":
                self.queue_label = value_label
            elif key == "processed":
                self.processed_label = value_label
            elif key == "session":
                self.session_label = value_label

    def _build_history_panel(self, parent: ttk.Frame) -> None:
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(
            header_frame, text="Recent Applications", font=("Segoe UI", 10, "bold")
        ).pack(side=tk.LEFT)

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.history_tree = ttk.Treeview(
            tree_frame,
            columns=("status", "job", "time", "error"),
            show="tree",
            selectmode="none",
        )

        self.history_tree.column("#0", width=0, stretch=False)
        self.history_tree.column("status", width=30, anchor=tk.CENTER, stretch=False)
        self.history_tree.column("job", width=400, anchor=tk.W)
        self.history_tree.column("time", width=80, anchor=tk.E, stretch=False)
        self.history_tree.column("error", width=200, anchor=tk.W)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)

        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.history_tree.tag_configure("success", foreground=SUCCESS_COLOR)
        self.history_tree.tag_configure("failed", foreground=ERROR_COLOR)
        self.history_tree.tag_configure("in_progress", foreground=WARNING_COLOR)
        self.history_tree.tag_configure("error_text", foreground=FG_DIM)

    def _build_log_panel(self, parent: ttk.Frame) -> None:
        self.log_container = ttk.Frame(parent)
        self.log_container.pack(fill=tk.X, pady=(0, 0))

        header_frame = ttk.Frame(self.log_container)
        header_frame.pack(fill=tk.X)

        self.log_toggle_btn = ttk.Button(
            header_frame,
            text="▶ Debug Log",
            style="Toggle.TButton",
            command=self._toggle_log,
        )
        self.log_toggle_btn.pack(side=tk.LEFT)

        self.log_frame = ttk.Frame(self.log_container)

        self.log_text = scrolledtext.ScrolledText(
            self.log_frame,
            wrap=tk.WORD,
            font=("Consolas", 8),
            state=tk.DISABLED,
            bg=BG_MEDIUM,
            fg=FG_DIM,
            insertbackground=FG_TEXT,
            selectbackground=ACCENT,
            selectforeground=BG_DARK,
            relief=tk.FLAT,
            borderwidth=0,
            padx=10,
            pady=10,
            height=8,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _toggle_log(self) -> None:
        if self._log_expanded:
            self.log_frame.pack_forget()
            self.log_toggle_btn.config(text="▶ Debug Log")
            self._log_expanded = False
        else:
            self.log_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
            self.log_toggle_btn.config(text="▼ Debug Log")
            self._log_expanded = True

    def _log(self, message: str) -> None:
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")

        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > MAX_LOG_LINES:
            self.log_text.delete("1.0", f"{line_count - MAX_LOG_LINES}.0")

        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _update_status(self, status: str, color: str = ACCENT) -> None:
        self.state.status = status
        self.status_text.config(text=status, foreground=color)

    def _update_current_job(self, job_title: str, company: str) -> None:
        if job_title and company:
            display = f"{job_title} @ {company}"
            if len(display) > 50:
                display = display[:47] + "..."
            self.state.current_job = display
            self.current_job_label.config(text=display)
        else:
            self.state.current_job = ""
            self.current_job_label.config(text="—")

    def _update_current_search(self, term: str) -> None:
        self.state.current_search = term
        self.current_search_label.config(text=term if term else "—")

    def _update_stats_bar(self) -> None:
        self.queue_label.config(text=f"{self.stats.queue_pending} pending")

        total = self.stats.jobs_applied
        success = self.stats.success_count
        failed = self.stats.failed_count
        self.processed_label.config(text=f"{total} ({success} ✓ {failed} ✗)")

    def _update_session_time(self) -> None:
        if self.state.session_start:
            elapsed = time.time() - self.state.session_start
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            self.session_label.config(text=f"{minutes}m {seconds}s")

        self.root.after(1000, self._update_session_time)

    def _add_history_entry(self, entry: HistoryEntry) -> None:
        self.state.history.insert(0, entry)
        if len(self.state.history) > MAX_HISTORY_ENTRIES:
            self.state.history = self.state.history[:MAX_HISTORY_ENTRIES]

        self._refresh_history_tree()

    def _update_history_entry(self, company: str, status: str, error: Optional[str] = None) -> None:
        for entry in self.state.history:
            if entry.company == company and entry.status == "in_progress":
                entry.status = status
                entry.error_reason = error
                entry.timestamp = time.time()
                break
        self._refresh_history_tree()

    def _refresh_history_tree(self) -> None:
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        now = time.time()
        for entry in self.state.history:
            status_icon = self._get_status_icon(entry.status)
            job_display = f"{entry.job_title} @ {entry.company}"
            if len(job_display) > 45:
                job_display = job_display[:42] + "..."

            time_ago = self._format_time_ago(now - entry.timestamp)
            error_display = f"({entry.error_reason})" if entry.error_reason else ""

            tag = entry.status
            self.history_tree.insert(
                "",
                tk.END,
                values=(status_icon, job_display, time_ago, error_display),
                tags=(tag,),
            )

    def _get_status_icon(self, status: str) -> str:
        icons = {
            "success": "✓",
            "failed": "✗",
            "in_progress": "⏳",
        }
        return icons.get(status, "?")

    def _format_time_ago(self, seconds: float) -> str:
        if seconds < 5:
            return "now"
        elif seconds < 60:
            return f"{int(seconds)}s ago"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m ago"
        else:
            return f"{int(seconds // 3600)}h ago"

    def _update_connection_status(self, connected: bool) -> None:
        if connected:
            self.status_label.config(text="🟢 Connected")
            self.connect_btn.config(text="Disconnect")
            self.control_btn.config(state=tk.NORMAL)
        else:
            self.status_label.config(text="⚪ Not Connected")
            self.connect_btn.config(text="Connect to Chrome")
            self.control_btn.config(state=tk.DISABLED)

    def _start_chrome(self) -> None:
        script = Path("scripts/start_chrome.bat")
        if not script.exists():
            self._log("Error: scripts/start_chrome.bat not found")
            return

        subprocess.Popen(["cmd", "/c", str(script)], shell=True)
        self._log("Starting Chrome... Wait a few seconds then click Connect.")

    def _connect_browser(self) -> None:
        if self.connection and self.connection.is_connected:
            if self.runner and self.runner.is_running:
                self._log("Stop automation before disconnecting")
                return

            self._agent = None
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
            self._init_agent()
        else:
            self._log(
                "Failed to connect. Make sure Chrome is running with --remote-debugging-port"
            )
            self.connection = None

    def _init_agent(self) -> None:
        if not self.connection or not self.connection.is_connected:
            logger.error("Cannot init agent: browser not connected")
            return

        try:
            tab_manager = TabManager(self.connection.browser)
            tab_manager.close_extras(keep=1)
            logger.info("Closed extra tabs from previous session")
            self._agent = ApplicationAgent(
                tab_manager=tab_manager,
                profile=self.profile.model_dump(),
                resume_path=self.profile.resume_path or None,
                claude_model=self.settings.claude.model,
            )
            logger.info("ApplicationAgent initialized on main thread")
            self._log("Application agent ready")
        except Exception as e:
            logger.exception("Failed to initialize ApplicationAgent")
            self._agent = None
            self._log(f"Warning: Agent init failed - {e}")

    def _toggle_automation(self) -> None:
        if self.runner and self.runner.is_running:
            self._stop_automation()
        else:
            self._start_automation()

    def _start_automation(self) -> None:
        if not self.connection or not self.connection.is_connected:
            self._log("Connect to Chrome first")
            return

        if self._agent is None:
            self._log("Reinitializing application agent...")
            self._init_agent()

        self.state.session_start = time.time()
        self.stats = DashboardStats()
        self._update_stats_bar()

        self.runner = AutomationRunner(
            profile=self.profile,
            settings=self.settings,
            apply_queue=self._apply_queue,
            result_queue=self._result_queue,
            on_progress=self._on_runner_progress,
        )

        if self.runner.start():
            self.control_btn.config(text="⏹  STOP", style="Stop.TButton")
            self.connect_btn.config(state=tk.DISABLED)
            self._update_status("Starting...", ACCENT)
            self._log("Automation started")
            self.root.after(APPLY_QUEUE_POLL_MS, self._process_apply_queue)

    def _stop_automation(self) -> None:
        if not self.runner:
            return

        self.runner.stop()
        self.control_btn.config(state=tk.DISABLED)
        self._update_status("Stopping...", FG_DIM)
        self._log("Stop requested, finishing current operation...")

    def _on_runner_progress(self, event: str, data: dict) -> None:
        self.message_queue.put((event, data))

    def _process_apply_queue(self) -> None:
        if not self.runner or not self.runner.is_running:
            logger.debug("Runner not active, stopping apply queue processor")
            return

        try:
            request = self._apply_queue.get_nowait()
        except Empty:
            self.root.after(APPLY_QUEUE_POLL_MS, self._process_apply_queue)
            return

        job = request.job
        logger.info(f"Processing apply request for {job.title} at {job.company}")

        if self._agent is None:
            logger.error("Agent not initialized, cannot process apply request")
            result = ApplyResult(
                job=job,
                success=False,
                error="Application agent not initialized",
            )
        else:
            try:
                app_result = self._agent.apply(job.url)
                success = app_result.status == ApplicationStatus.SUCCESS

                if app_result.status == ApplicationStatus.NEEDS_LOGIN:
                    logger.error(f"[STOPPING] {app_result.message}")
                    self._on_login_required(app_result.message)

                result = ApplyResult(
                    job=job,
                    success=success,
                    error=None if success else app_result.message,
                )
                logger.info(
                    f"Apply result for {job.company}: "
                    f"{'success' if success else app_result.message}"
                )
            except Exception as e:
                logger.exception(f"Apply error for {job.url}")
                result = ApplyResult(
                    job=job,
                    success=False,
                    error=str(e),
                )

        self._result_queue.put(result)
        logger.debug(f"ApplyResult sent to result_queue for {job.url}")

        self.root.after(APPLY_QUEUE_POLL_MS, self._process_apply_queue)

    def _process_messages(self) -> None:
        try:
            while True:
                msg_type, data = self.message_queue.get_nowait()
                self._handle_message(msg_type, data)
        except Empty:
            pass

        self.root.after(MESSAGE_POLL_MS, self._process_messages)

    def _handle_message(self, msg_type: str, data) -> None:
        if msg_type == "log":
            self._log(data)

        elif msg_type == "started":
            self._update_status("Searching...", ACCENT)

        elif msg_type == "stopped":
            self._on_automation_stopped(data)

        elif msg_type == "search_start":
            term = data.get("term", "")
            self._update_status(StatusState.SEARCHING, ACCENT)
            self._update_current_search(term)
            self._update_current_job("", "")
            self._log(f"Searching for: {term}")

        elif msg_type == "search_complete":
            self._on_search_complete(data)

        elif msg_type == "search_failed":
            term = data.get("term", "")
            error = data.get("error", "Unknown error")
            self._update_status(f"Search failed: {error[:30]}", ERROR_COLOR)
            self._log(f"Search failed for '{term}': {error}")

        elif msg_type == "apply_start":
            job = data.get("job", {})
            title = job.get("title", "Unknown")
            company = job.get("company", "Unknown")
            self._update_status(StatusState.NAVIGATING, ACCENT)
            self._update_current_job(title, company)
            self._log(f"Applying to: {title} at {company}")

            entry = HistoryEntry(
                job_title=title,
                company=company,
                status="in_progress",
                timestamp=time.time(),
            )
            self._add_history_entry(entry)

        elif msg_type == "form_progress":
            page = data.get("page", 1)
            total = data.get("total", "?")
            self._update_status(f"Filling form (page {page}/{total})...", ACCENT)

        elif msg_type == "apply_complete":
            self._on_apply_complete(data)

        elif msg_type == "apply_failed":
            self._on_apply_failed(data)

        elif msg_type == "cycle_complete":
            term = data.get("search_term", "")
            self._log(f"Cycle complete for: {term}")
            self._update_status(StatusState.IDLE, FG_DIM)

        elif msg_type == "error":
            error = data.get("message", "Unknown error")
            self._log(f"ERROR: {error}")
            self._update_status(f"Error: {error[:40]}", ERROR_COLOR)

        elif msg_type == "queue_update":
            self.stats.queue_pending = data.get("pending", 0)
            self._update_stats_bar()

    def _on_automation_stopped(self, data: dict) -> None:
        self.control_btn.config(text="▶  START", style="Start.TButton", state=tk.NORMAL)
        self.connect_btn.config(state=tk.NORMAL)
        self._update_status(StatusState.IDLE, FG_DIM)
        self._update_current_job("", "")
        self._update_current_search("")
        self._log("Automation stopped")

        stats = data.get("stats", {})
        self._log(
            f"Session summary: Found {stats.get('jobs_found', 0)}, "
            f"Applied {stats.get('jobs_applied', 0)}, "
            f"Success {stats.get('success_count', 0)}, "
            f"Failed {stats.get('failed_count', 0)}"
        )

    def _on_search_complete(self, data: dict) -> None:
        term = data.get("term", "")
        found = data.get("found", 0)
        passed = data.get("passed", 0)
        added = data.get("added", 0)

        self.stats.jobs_found += found
        self.stats.queue_pending += added
        self._update_stats_bar()

        self._log(f"Found {found} jobs for '{term}', {passed} passed filter, {added} added to queue")

    def _on_apply_complete(self, data: dict) -> None:
        job = data.get("job", {})
        company = job.get("company", "Unknown")

        self.stats.jobs_applied += 1
        self.stats.success_count += 1
        self.stats.queue_pending = max(0, self.stats.queue_pending - 1)
        self._update_stats_bar()

        self._update_history_entry(company, "success")
        self._update_status(StatusState.COMPLETE, SUCCESS_COLOR)
        self._log(f"✓ Successfully applied to {company}")

    def _on_apply_failed(self, data: dict) -> None:
        job = data.get("job", {})
        company = job.get("company", "Unknown")
        result = data.get("result", {})
        error = data.get("error", result.get("message", "Unknown error"))

        self.stats.jobs_applied += 1
        self.stats.failed_count += 1
        self.stats.queue_pending = max(0, self.stats.queue_pending - 1)
        self._update_stats_bar()

        short_error = error[:40] if len(error) > 40 else error
        self._update_history_entry(company, "failed", short_error)
        self._update_status(StatusState.ERROR, ERROR_COLOR)
        self._log(f"✗ Failed to apply to {company}: {error}")

    def _on_login_required(self, message: str) -> None:
        self._log(f"⚠️ {message}")
        self._update_status(f"⚠️ {message[:40]}", ERROR_COLOR)

        if self.runner and self.runner.is_running:
            self.runner.stop()

    def run(self) -> None:
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
