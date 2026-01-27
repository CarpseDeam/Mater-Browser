from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from src.feedback.failure_logger import ApplicationFailure, FailureLogger
from src.feedback.failure_summarizer import FailureSummarizer
from src.feedback.config_suggester import ConfigSuggester, FixSuggestion

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

BRIDGE_URL = "http://localhost:5001/dispatch"


@dataclass
class RepairSpec:
    description: str
    suggestions: list[FixSuggestion]


class AutoRepairer:
    def __init__(self, threshold: int = 5, cooldown_minutes: int = 10) -> None:
        self._threshold = threshold
        self._cooldown_minutes = cooldown_minutes
        self._failure_count = 0
        self._last_repair_time: float | None = None
        self._failure_logger = FailureLogger()
        self._counter_lock = threading.Lock()

    def record_failure(self, failure: ApplicationFailure) -> None:
        with self._counter_lock:
            self._failure_count += 1
        self._failure_logger.log(failure)

    def maybe_repair(self) -> bool:
        with self._counter_lock:
            if self._failure_count < self._threshold:
                return False

        if self._is_in_cooldown():
            return False

        failures = self._failure_logger.read_all(include_addressed=False)
        if not failures:
            return False

        spec = self._generate_spec(failures)
        if not spec.suggestions:
            return False

        logger.info(
            f"Triggering auto-repair: {self._failure_count} failures, "
            f"{len(spec.suggestions)} suggestions"
        )

        thread = threading.Thread(
            target=self._dispatch_repair_sync,
            args=(spec, failures),
            daemon=True
        )
        thread.start()
        self._last_repair_time = time.time()
        return True

    def reset(self) -> None:
        with self._counter_lock:
            self._failure_count = 0

    def _is_in_cooldown(self) -> bool:
        if self._last_repair_time is None:
            return False
        elapsed = time.time() - self._last_repair_time
        cooldown_seconds = self._cooldown_minutes * 60
        return elapsed < cooldown_seconds

    def _generate_spec(self, failures: list[ApplicationFailure]) -> RepairSpec:
        summarizer = FailureSummarizer(failures)
        summaries = summarizer.summarize()

        suggester = ConfigSuggester()
        suggestions = suggester.suggest(summaries)

        failure_types = set(f.failure_type for f in failures)
        description = (
            f"Auto-repair for {len(failures)} failures. "
            f"Types: {', '.join(sorted(failure_types))}"
        )

        return RepairSpec(description=description, suggestions=suggestions)

    def _generate_prompt(self, suggestions: list[FixSuggestion]) -> str:
        lines = ["# Fix Suggestions for Failure Feedback System", ""]

        for i, suggestion in enumerate(suggestions, 1):
            lines.append(f"## {i}. {suggestion.fix_type}: {suggestion.description}")
            lines.append(f"**Target file:** `{suggestion.target_file}`")
            lines.append(f"**Failure count:** {suggestion.failure_count}")
            lines.append("")
            lines.append("```")
            lines.append(suggestion.suggested_content)
            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    def _dispatch_repair_sync(
        self, spec: RepairSpec, failures: list[ApplicationFailure]
    ) -> None:
        spec_content = self._generate_prompt(spec.suggestions)
        payload = {
            "spec": spec_content,
            "project_path": str(Path(__file__).parent.parent.parent.resolve()),
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(BRIDGE_URL, json=payload)
                if response.status_code == 200:
                    logger.info(f"Repair dispatched successfully: {spec.description}")
                    timestamps = [f.timestamp for f in failures]
                    self._failure_logger.mark_addressed(timestamps)
                    self.reset()
                else:
                    logger.error(
                        f"Repair dispatch failed with status {response.status_code}: "
                        f"{response.text}"
                    )
        except httpx.ConnectError:
            logger.warning(
                "Bridge server not available at %s, skipping repair", BRIDGE_URL
            )
        except httpx.TimeoutException:
            logger.warning("Bridge server timed out, skipping repair")
        except Exception as e:
            logger.error(f"Unexpected error during repair dispatch: {e}")
