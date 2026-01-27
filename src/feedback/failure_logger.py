from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

FailureType = Literal[
    "unknown_question",
    "stuck_loop",
    "validation_error",
    "timeout",
    "crash",
    "react_select_fail",
]

DEFAULT_LOG_PATH = Path("data/failures.jsonl")


@dataclass
class ApplicationFailure:
    timestamp: str
    job_url: str
    job_title: str
    company: str
    failure_type: FailureType
    details: dict[str, Any]
    page_snapshot: str | None = None
    addressed: bool = False


class FailureLogger:
    def __init__(self, log_path: Path | None = None) -> None:
        self._log_path = log_path or DEFAULT_LOG_PATH
        self._lock = threading.Lock()

    def _ensure_directory(self) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def _serialize(self, failure: ApplicationFailure) -> str:
        data = asdict(failure)
        return json.dumps(data, default=str)

    def log(self, failure: ApplicationFailure) -> None:
        self._ensure_directory()
        line = self._serialize(failure) + "\n"
        with self._lock:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line)

    def read_all(self, include_addressed: bool = False) -> list[ApplicationFailure]:
        if not self._log_path.exists():
            return []

        failures: list[ApplicationFailure] = []
        with open(self._log_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    failure = ApplicationFailure(**data)
                    if include_addressed or not failure.addressed:
                        failures.append(failure)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Skipping malformed line {line_num}: {e}")
        return failures

    def mark_addressed(self, timestamps: list[str]) -> None:
        if not self._log_path.exists():
            return

        timestamp_set = set(timestamps)
        updated_lines: list[str] = []

        with self._lock:
            with open(self._log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("timestamp") in timestamp_set:
                            data["addressed"] = True
                        updated_lines.append(json.dumps(data, default=str))
                    except json.JSONDecodeError:
                        updated_lines.append(line)

            with open(self._log_path, "w", encoding="utf-8") as f:
                for line in updated_lines:
                    f.write(line + "\n")
