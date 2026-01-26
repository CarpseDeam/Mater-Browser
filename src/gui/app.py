"""Main GUI application for Mater-Browser."""
import json
import logging
import subprocess
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from tkinter import messagebox, scrolledtext, ttk
from typing import Optional

from ..agent.application import ApplicationAgent
from ..agent.models import ApplicationStatus
from ..browser.connection import BrowserConnection
from ..browser.tabs import TabManager
from ..core.config import Settings
from ..core.logging import setup_logging
from ..profile.manager import load_profile
from ..queue import JobQueue
from ..scraper import JobScorer, JobSpyClient

logger = logging.getLogger(__name__)


class LogHandler(logging.Handler):
    """Custom handler to send logs to GUI queue."""

    def __init__(self, queue: Queue) -> None:
        super().__init__()
        self.queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.queue.put(("log", msg))


class MaterBrowserApp:
    """Main GUI application."""

    HISTORY_FILE = Path("data/job_history.json")

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Mater-Browser - Job Application Agent")
        self.root.geometry("900x700")
        self.root.minsize(700, 500)

        # State
        self.connection: Optional[BrowserConnection] = None
        self.is_running = False
        self.current_thread: Optional[threading.Thread] = None
        self.message_queue: Queue = Queue()
        self.job_history: list[dict] = []

        # Bulk apply state
        self.job_queue = JobQueue()
        self.scraper = JobSpyClient()
        self.bulk_running = False
        self.bulk_stop_flag = False

        # Load config
        self.settings = Settings.from_yaml(Path("config/settings.yaml"))
        self.profile = load_profile(Path("config/profile.yaml"))

        # Scorer with profile
        self.scorer = JobScorer(self.profile.model_dump())

        # Setup logging to GUI
        setup_logging("INFO")
        log_handler = LogHandler(self.message_queue)
        log_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(message)s", "%H:%M:%S")
        )
        logging.getLogger().addHandler(log_handler)

        # Build UI
        self._build_ui()

        # Load history
        self._load_history()

        # Update queue display
        self._update_queue_display()

        # Start message processing
        self._process_messages()

    def _build_ui(self) -> None:
        """Build the user interface."""
        bg_dark = "#1e1e1e"
        bg_medium = "#2d2d2d"
        bg_light = "#3c3c3c"
        fg_text = "#e0e0e0"
        fg_dim = "#a0a0a0"
        accent = "#4fc3f7"

        self.root.configure(bg=bg_dark)

        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background=bg_dark)
        style.configure("TLabel", background=bg_dark, foreground=fg_text)

        style.configure(
            "TButton",
            background=bg_light,
            foreground=fg_text,
            borderwidth=1,
            focuscolor=bg_light,
            padding=(10, 5),
        )
        style.map(
            "TButton",
            background=[("active", bg_medium), ("disabled", bg_dark)],
            foreground=[("disabled", fg_dim)],
        )

        style.configure(
            "TEntry",
            fieldbackground=bg_medium,
            foreground=fg_text,
            insertcolor=fg_text,
            borderwidth=1,
            padding=5,
        )

        style.configure("TNotebook", background=bg_dark, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=bg_medium,
            foreground=fg_text,
            padding=(15, 8),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", bg_light)],
            foreground=[("selected", accent)],
        )

        style.configure(
            "Treeview",
            background=bg_medium,
            foreground=fg_text,
            fieldbackground=bg_medium,
            borderwidth=0,
            rowheight=25,
        )
        style.configure(
            "Treeview.Heading",
            background=bg_light,
            foreground=fg_text,
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", bg_light)],
            foreground=[("selected", accent)],
        )

        style.configure(
            "Vertical.TScrollbar",
            background=bg_light,
            troughcolor=bg_dark,
            borderwidth=0,
            arrowsize=14,
        )

        style.configure("TCheckbutton", background=bg_dark, foreground=fg_text)
        style.configure("TSpinbox", fieldbackground=bg_medium, foreground=fg_text)

        self._colors = {
            "bg_dark": bg_dark,
            "bg_medium": bg_medium,
            "fg_text": fg_text,
            "accent": accent,
        }

        # Main container
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # === Top: Connection Status ===
        status_frame = ttk.Frame(main)
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_label = ttk.Label(status_frame, text="⚪ Not Connected")
        self.status_label.pack(side=tk.LEFT)

        self.connect_btn = ttk.Button(
            status_frame, text="Connect to Chrome", command=self._connect_browser
        )
        self.connect_btn.pack(side=tk.LEFT, padx=(10, 0))

        self.start_chrome_btn = ttk.Button(
            status_frame, text="Start Chrome", command=self._start_chrome
        )
        self.start_chrome_btn.pack(side=tk.LEFT, padx=(5, 0))

        # === URL Input (for single job) ===
        url_frame = ttk.Frame(main)
        url_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(url_frame, text="Job URL:").pack(side=tk.LEFT)

        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 10))
        self.url_entry.bind("<Return>", lambda e: self._apply())

        self.apply_btn = ttk.Button(
            url_frame, text="Apply", command=self._apply, state=tk.DISABLED
        )
        self.apply_btn.pack(side=tk.RIGHT)

        # === Notebook for tabs ===
        notebook = ttk.Notebook(main)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Log
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="Activity Log")

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED,
            bg=self._colors["bg_medium"],
            fg=self._colors["fg_text"],
            insertbackground=self._colors["fg_text"],
            selectbackground=self._colors["accent"],
            selectforeground=self._colors["bg_dark"],
            relief=tk.FLAT,
            borderwidth=0,
            padx=10,
            pady=10,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Tab 2: Search Jobs
        search_frame = ttk.Frame(notebook, padding=10)
        notebook.add(search_frame, text="Search Jobs")
        self._build_search_tab(search_frame)

        # Tab 3: Job Queue
        queue_frame = ttk.Frame(notebook)
        notebook.add(queue_frame, text="Job Queue")
        self._build_queue_tab(queue_frame)

        # Tab 4: Job History
        history_frame = ttk.Frame(notebook)
        notebook.add(history_frame, text="Job History")

        columns = ("time", "url", "status", "pages")
        self.history_tree = ttk.Treeview(
            history_frame, columns=columns, show="headings", selectmode="browse"
        )

        self.history_tree.heading("time", text="Time")
        self.history_tree.heading("url", text="URL")
        self.history_tree.heading("status", text="Status")
        self.history_tree.heading("pages", text="Pages")

        self.history_tree.column("time", width=80)
        self.history_tree.column("url", width=400)
        self.history_tree.column("status", width=100)
        self.history_tree.column("pages", width=50)

        scrollbar = ttk.Scrollbar(
            history_frame, orient=tk.VERTICAL, command=self.history_tree.yview
        )
        self.history_tree.configure(yscrollcommand=scrollbar.set)

        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Tab 5: Profile
        profile_frame = ttk.Frame(notebook, padding=10)
        notebook.add(profile_frame, text="Profile")

        skills_display = ", ".join(self.profile.skills[:10])
        if len(self.profile.skills) > 10:
            skills_display += "..."

        profile_text = f"""Name: {self.profile.first_name} {self.profile.last_name}
Email: {self.profile.email}
Phone: {self.profile.phone}
Location: {self.profile.location}

Title: {self.profile.current_title}
Experience: {self.profile.years_experience} years
Skills: {skills_display}

Resume: {self.profile.resume_path or 'Not set'}"""

        ttk.Label(profile_frame, text=profile_text, justify=tk.LEFT).pack(anchor=tk.W)

        # === Bottom: Stats ===
        stats_frame = ttk.Frame(main)
        stats_frame.pack(fill=tk.X, pady=(10, 0))

        self.stats_label = ttk.Label(
            stats_frame, text="Applied: 0 | Success: 0 | Failed: 0"
        )
        self.stats_label.pack(side=tk.LEFT)

        ttk.Button(stats_frame, text="Clear Log", command=self._clear_log).pack(
            side=tk.RIGHT
        )

    def _build_search_tab(self, parent: ttk.Frame) -> None:
        """Build the search tab UI."""
        # Search inputs grid
        input_frame = ttk.Frame(parent)
        input_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(input_frame, text="Job Title/Keywords:").grid(
            row=0, column=0, sticky="w", pady=5
        )
        self.search_term = ttk.Entry(input_frame, width=40)
        self.search_term.grid(row=0, column=1, pady=5, padx=(10, 0), sticky="w")
        self.search_term.insert(0, "Python Engineer")

        ttk.Label(input_frame, text="Location:").grid(row=1, column=0, sticky="w", pady=5)
        self.search_location = ttk.Entry(input_frame, width=40)
        self.search_location.grid(row=1, column=1, pady=5, padx=(10, 0), sticky="w")
        self.search_location.insert(0, "remote")

        self.remote_only = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            input_frame, text="Remote Only", variable=self.remote_only
        ).grid(row=2, column=1, sticky="w", pady=5, padx=(10, 0))

        ttk.Label(input_frame, text="Max Results:").grid(
            row=3, column=0, sticky="w", pady=5
        )
        self.max_results = ttk.Spinbox(input_frame, from_=10, to=100, width=10)
        self.max_results.grid(row=3, column=1, sticky="w", pady=5, padx=(10, 0))
        self.max_results.set(50)

        ttk.Label(input_frame, text="Min Score:").grid(
            row=4, column=0, sticky="w", pady=5
        )
        self.min_score = ttk.Spinbox(
            input_frame, from_=0.0, to=1.0, increment=0.1, width=10
        )
        self.min_score.grid(row=4, column=1, sticky="w", pady=5, padx=(10, 0))
        self.min_score.set(0.3)

        # Sites selection
        ttk.Label(input_frame, text="Sites:").grid(row=5, column=0, sticky="w", pady=5)
        sites_frame = ttk.Frame(input_frame)
        sites_frame.grid(row=5, column=1, sticky="w", pady=5, padx=(10, 0))

        self.site_linkedin = tk.BooleanVar(value=True)
        self.site_indeed = tk.BooleanVar(value=True)
        self.site_glassdoor = tk.BooleanVar(value=True)
        self.site_zip = tk.BooleanVar(value=False)

        ttk.Checkbutton(sites_frame, text="LinkedIn", variable=self.site_linkedin).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        ttk.Checkbutton(sites_frame, text="Indeed", variable=self.site_indeed).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        ttk.Checkbutton(sites_frame, text="Glassdoor", variable=self.site_glassdoor).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        ttk.Checkbutton(
            sites_frame, text="ZipRecruiter", variable=self.site_zip
        ).pack(side=tk.LEFT)

        # Search button
        self.search_btn = ttk.Button(
            input_frame, text="Search Jobs", command=self._search_jobs
        )
        self.search_btn.grid(row=6, column=1, sticky="w", pady=20, padx=(10, 0))

        # Search results info
        self.search_status = ttk.Label(parent, text="")
        self.search_status.pack(anchor=tk.W)

    def _build_queue_tab(self, parent: ttk.Frame) -> None:
        """Build the queue tab UI."""
        # Queue controls
        queue_controls = ttk.Frame(parent)
        queue_controls.pack(fill=tk.X, pady=5, padx=5)

        self.queue_stats = ttk.Label(queue_controls, text="Queue: 0 pending")
        self.queue_stats.pack(side=tk.LEFT)

        self.bulk_btn = ttk.Button(
            queue_controls, text="▶ Start Bulk Apply", command=self._toggle_bulk_apply
        )
        self.bulk_btn.pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            queue_controls, text="Clear Pending", command=self._clear_queue
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            queue_controls, text="Refresh", command=self._update_queue_display
        ).pack(side=tk.RIGHT)

        # Queue list
        columns = ("score", "title", "company", "site", "status")
        self.queue_tree = ttk.Treeview(
            parent, columns=columns, show="headings", selectmode="browse"
        )
        self.queue_tree.heading("score", text="Score")
        self.queue_tree.heading("title", text="Title")
        self.queue_tree.heading("company", text="Company")
        self.queue_tree.heading("site", text="Site")
        self.queue_tree.heading("status", text="Status")

        self.queue_tree.column("score", width=60)
        self.queue_tree.column("title", width=300)
        self.queue_tree.column("company", width=150)
        self.queue_tree.column("site", width=80)
        self.queue_tree.column("status", width=80)

        queue_scroll = ttk.Scrollbar(
            parent, orient=tk.VERTICAL, command=self.queue_tree.yview
        )
        self.queue_tree.configure(yscrollcommand=queue_scroll.set)
        self.queue_tree.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5
        )
        queue_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=5, padx=(0, 5))

    def _log(self, message: str) -> None:
        """Add message to log."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _clear_log(self) -> None:
        """Clear the log."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _update_status(self, connected: bool) -> None:
        """Update connection status."""
        if connected:
            self.status_label.config(text="🟢 Connected")
            self.apply_btn.config(state=tk.NORMAL)
            self.connect_btn.config(text="Disconnect")
        else:
            self.status_label.config(text="⚪ Not Connected")
            self.apply_btn.config(state=tk.DISABLED)
            self.connect_btn.config(text="Connect to Chrome")

    def _update_stats(self) -> None:
        """Update stats label."""
        total = len(self.job_history)
        success = sum(1 for j in self.job_history if j.get("status") == "success")
        failed = total - success
        self.stats_label.config(
            text=f"Applied: {total} | Success: {success} | Failed: {failed}"
        )

    def _start_chrome(self) -> None:
        """Start Chrome with debugging port."""
        script = Path("scripts/start_chrome.bat")
        if script.exists():
            subprocess.Popen(["cmd", "/c", str(script)], shell=True)
            self._log("Starting Chrome... Wait a few seconds then click Connect.")
        else:
            self._log("Error: scripts/start_chrome.bat not found")

    def _connect_browser(self) -> None:
        """Connect or disconnect from browser."""
        if self.connection and self.connection.is_connected:
            self.connection.disconnect()
            self.connection = None
            self._update_status(False)
            self._log("Disconnected from Chrome")
            return

        self._log("Connecting to Chrome...")

        self.connection = BrowserConnection(
            cdp_port=self.settings.browser.cdp_port,
            max_retries=3,
            retry_delay=1.0,
        )

        if self.connection.connect():
            self._update_status(True)
            self._log("Connected to Chrome!")
        else:
            self._log(
                "Failed to connect. Make sure Chrome is running with --remote-debugging-port=9333"
            )
            self.connection = None

    def _apply(self) -> None:
        """Start application process for single URL."""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Please enter a job URL")
            return

        if not self.connection or not self.connection.is_connected:
            messagebox.showwarning("Not Connected", "Connect to Chrome first")
            return

        if self.is_running:
            self._log("Already running an application...")
            return

        self.is_running = True
        self.apply_btn.config(state=tk.DISABLED)
        self.current_thread = threading.Thread(target=self._run_application, args=(url,))
        self.current_thread.start()

    def _run_application(self, url: str) -> None:
        """Run application in background thread."""
        try:
            tabs = TabManager(self.connection.browser)

            agent = ApplicationAgent(
                tab_manager=tabs,
                profile=self.profile.model_dump(),
                resume_path=self.profile.resume_path or None,
                max_pages=15,
                claude_model=self.settings.claude.model,
            )

            result = agent.apply(url)

            record = {
                "time": datetime.now().isoformat(),
                "url": url,
                "status": result.status.value,
                "pages": result.pages_processed,
                "message": result.message,
            }

            self.message_queue.put(("result", record))

        except Exception as e:
            logger.error(f"Application error: {e}")
            self.message_queue.put(("error", str(e)))

        finally:
            self.message_queue.put(("done", None))

    def _search_jobs(self) -> None:
        """Search for jobs and add to queue."""
        term = self.search_term.get().strip()
        location = self.search_location.get().strip()
        remote = self.remote_only.get()
        max_results = int(self.max_results.get())
        min_score = float(self.min_score.get())

        if not term:
            messagebox.showwarning("No Search Term", "Please enter a job title/keywords")
            return

        # Build sites list
        sites = []
        if self.site_linkedin.get():
            sites.append("linkedin")
        if self.site_indeed.get():
            sites.append("indeed")
        if self.site_glassdoor.get():
            sites.append("glassdoor")
        if self.site_zip.get():
            sites.append("zip_recruiter")

        if not sites:
            messagebox.showwarning("No Sites", "Please select at least one job site")
            return

        self.search_btn.config(state=tk.DISABLED)
        self.search_status.config(text=f"Searching for '{term}'...")
        self._log(f"Searching: {term} in {location}...")

        def do_search():
            try:
                self.scraper.sites = sites
                self.scraper.results_wanted = max_results
                jobs = self.scraper.search(term, location, remote)

                self.scorer.min_score = min_score
                scored = self.scorer.filter_and_score(jobs)

                added = self.job_queue.add_many(scored)
                self.message_queue.put(("search_done", (len(jobs), len(scored), added)))
            except Exception as e:
                logger.error(f"Search error: {e}")
                self.message_queue.put(("search_error", str(e)))

        threading.Thread(target=do_search).start()

    def _update_queue_display(self) -> None:
        """Update queue treeview."""
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)

        for job in self.job_queue.get_all():
            self.queue_tree.insert(
                "",
                "end",
                values=(
                    f"{job.score:.0%}",
                    job.title[:50] if len(job.title) > 50 else job.title,
                    job.company[:25] if len(job.company) > 25 else job.company,
                    job.site,
                    job.status,
                ),
            )

        stats = self.job_queue.stats()
        self.queue_stats.config(
            text=f"Queue: {stats['pending']} pending | {stats['applied']} applied | {stats['failed']} failed"
        )

    def _toggle_bulk_apply(self) -> None:
        """Start or stop bulk apply."""
        if self.bulk_running:
            self.bulk_stop_flag = True
            self.bulk_btn.config(text="Stopping...")
        else:
            if not self.connection or not self.connection.is_connected:
                messagebox.showwarning("Not Connected", "Connect to Chrome first")
                return

            pending = self.job_queue.get_pending()
            if not pending:
                messagebox.showinfo("Empty Queue", "No pending jobs in queue")
                return

            self.bulk_running = True
            self.bulk_stop_flag = False
            self.bulk_btn.config(text="⏹ Stop")
            threading.Thread(target=self._bulk_apply_loop).start()

    def _bulk_apply_loop(self) -> None:
        """Main bulk apply loop."""
        try:
            tabs = TabManager(self.connection.browser)
            agent = ApplicationAgent(
                tab_manager=tabs,
                profile=self.profile.model_dump(),
                resume_path=self.profile.resume_path or None,
                max_pages=15,
                claude_model=self.settings.claude.model,
            )

            while not self.bulk_stop_flag:
                job = self.job_queue.get_next()
                if not job:
                    self._log("No more jobs in queue")
                    break

                self._log(f"Applying: {job.title} at {job.company}")

                try:
                    result = agent.apply(job.url)

                    if result.status == ApplicationStatus.SUCCESS:
                        self.job_queue.mark_applied(job.url)
                        self._log(f"✓ Applied to {job.company}")

                        record = {
                            "time": datetime.now().isoformat(),
                            "url": job.url,
                            "status": result.status.value,
                            "pages": result.pages_processed,
                            "message": result.message,
                        }
                        self.job_history.append(record)
                        self._save_history()
                    elif result.status == ApplicationStatus.NEEDS_LOGIN:
                        self.job_queue.mark_failed(job.url, result.message)
                        self._log(f"⚠️ [STOPPING] {result.message}")
                        self.bulk_stop_flag = True
                        break
                    else:
                        self.job_queue.mark_failed(job.url, result.message)
                        self._log(f"✗ Failed: {result.message}")

                    self.message_queue.put(("queue_update", None))

                except Exception as e:
                    self.job_queue.mark_failed(job.url, str(e))
                    self._log(f"Error: {e}")

                time.sleep(2)

        except Exception as e:
            logger.error(f"Bulk apply error: {e}")

        finally:
            self.message_queue.put(("bulk_done", None))

    def _clear_queue(self) -> None:
        """Clear pending jobs from queue."""
        self.job_queue.clear_pending()
        self._update_queue_display()
        self._log("Cleared pending jobs from queue")

    def _process_messages(self) -> None:
        """Process messages from worker thread."""
        try:
            while True:
                msg_type, data = self.message_queue.get_nowait()

                if msg_type == "log":
                    self._log(data)

                elif msg_type == "result":
                    self.job_history.append(data)
                    self._save_history()
                    self._update_history_tree()
                    self._update_stats()

                    status = data["status"]
                    if status == "success":
                        self._log(f"✓ SUCCESS: {data['message']}")
                    else:
                        self._log(f"✗ {status.upper()}: {data['message']}")

                elif msg_type == "error":
                    self._log(f"ERROR: {data}")

                elif msg_type == "done":
                    self.is_running = False
                    self.apply_btn.config(state=tk.NORMAL)
                    self.url_entry.delete(0, tk.END)

                elif msg_type == "search_done":
                    found, scored, added = data
                    self._log(
                        f"Found {found} jobs, {scored} passed scoring, {added} added to queue"
                    )
                    self.search_status.config(
                        text=f"Found {found} jobs, {scored} passed filter, {added} new added"
                    )
                    self._update_queue_display()
                    self.search_btn.config(state=tk.NORMAL)

                elif msg_type == "search_error":
                    self._log(f"Search error: {data}")
                    self.search_status.config(text=f"Error: {data}")
                    self.search_btn.config(state=tk.NORMAL)

                elif msg_type == "queue_update":
                    self._update_queue_display()
                    self._update_history_tree()
                    self._update_stats()

                elif msg_type == "bulk_done":
                    self.bulk_running = False
                    self.bulk_btn.config(text="▶ Start Bulk Apply")
                    self._update_queue_display()
                    self._update_stats()

        except Empty:
            pass

        self.root.after(100, self._process_messages)

    def _update_history_tree(self) -> None:
        """Update history treeview."""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        for job in reversed(self.job_history[-100:]):
            time_str = datetime.fromisoformat(job["time"]).strftime("%H:%M:%S")
            url = job["url"][:60] + "..." if len(job["url"]) > 60 else job["url"]

            self.history_tree.insert(
                "", "end", values=(time_str, url, job["status"], job["pages"])
            )

    def _load_history(self) -> None:
        """Load job history from file."""
        if self.HISTORY_FILE.exists():
            try:
                with open(self.HISTORY_FILE) as f:
                    self.job_history = json.load(f)
                self._update_history_tree()
                self._update_stats()
            except Exception:
                self.job_history = []

    def _save_history(self) -> None:
        """Save job history to file."""
        self.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.HISTORY_FILE, "w") as f:
            json.dump(self.job_history, f, indent=2)

    def run(self) -> None:
        """Run the application."""
        self._log("Mater-Browser GUI started")
        self._log("Click 'Start Chrome' then 'Connect to Chrome' to begin")
        self._log("Use 'Search Jobs' tab to find jobs, 'Job Queue' to manage bulk apply")
        self.root.mainloop()

        if self.connection:
            self.connection.disconnect()
