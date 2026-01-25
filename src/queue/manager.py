"""Job queue management with persistence."""
import json
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

from ..scraper.jobspy_client import JobListing

logger = logging.getLogger(__name__)


class JobQueue:
    """Manages queue of jobs to apply to."""

    QUEUE_FILE = Path("data/job_queue.json")

    def __init__(self) -> None:
        self._jobs: dict[str, JobListing] = {}
        self._lock = Lock()
        self._load()

    def add(self, job: JobListing) -> bool:
        """Add job to queue if not already present."""
        with self._lock:
            if job.url in self._jobs:
                return False
            self._jobs[job.url] = job
            self._save()
            return True

    def add_many(self, jobs: list[JobListing]) -> int:
        """Add multiple jobs, returns count added."""
        added = 0
        with self._lock:
            for job in jobs:
                if job.url not in self._jobs:
                    self._jobs[job.url] = job
                    added += 1
            self._save()
        return added

    def get_next(self) -> Optional[JobListing]:
        """Get next pending job with highest score."""
        with self._lock:
            pending = [j for j in self._jobs.values() if j.status == "pending"]
            if not pending:
                return None
            pending.sort(key=lambda j: j.score, reverse=True)
            return pending[0]

    def get_pending(self) -> list[JobListing]:
        """Get all pending jobs sorted by score."""
        with self._lock:
            pending = [j for j in self._jobs.values() if j.status == "pending"]
            pending.sort(key=lambda j: j.score, reverse=True)
            return pending

    def get_all(self) -> list[JobListing]:
        """Get all jobs."""
        with self._lock:
            return list(self._jobs.values())

    def mark_applied(self, url: str) -> None:
        """Mark job as applied."""
        with self._lock:
            if url in self._jobs:
                self._jobs[url].status = "applied"
                self._jobs[url].applied_at = datetime.now()
                self._save()

    def mark_failed(self, url: str, error: str) -> None:
        """Mark job as failed."""
        with self._lock:
            if url in self._jobs:
                self._jobs[url].status = "failed"
                self._jobs[url].error = error
                self._save()

    def mark_skipped(self, url: str, reason: str) -> None:
        """Mark job as skipped."""
        with self._lock:
            if url in self._jobs:
                self._jobs[url].status = "skipped"
                self._jobs[url].error = reason
                self._save()

    def clear_pending(self) -> None:
        """Clear all pending jobs."""
        with self._lock:
            self._jobs = {k: v for k, v in self._jobs.items() if v.status != "pending"}
            self._save()

    def stats(self) -> dict:
        """Get queue statistics."""
        with self._lock:
            jobs = list(self._jobs.values())
            return {
                "total": len(jobs),
                "pending": sum(1 for j in jobs if j.status == "pending"),
                "applied": sum(1 for j in jobs if j.status == "applied"),
                "failed": sum(1 for j in jobs if j.status == "failed"),
                "skipped": sum(1 for j in jobs if j.status == "skipped"),
            }

    def _save(self) -> None:
        """Save queue to disk."""
        self.QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)

        data = []
        for job in self._jobs.values():
            d = {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "url": job.url,
                "description": job.description[:500],
                "salary": job.salary,
                "date_posted": job.date_posted.isoformat() if job.date_posted else None,
                "site": job.site,
                "is_remote": job.is_remote,
                "job_type": job.job_type,
                "score": job.score,
                "status": job.status,
                "applied_at": job.applied_at.isoformat() if job.applied_at else None,
                "error": job.error,
            }
            data.append(d)

        with open(self.QUEUE_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self) -> None:
        """Load queue from disk."""
        if not self.QUEUE_FILE.exists():
            return

        try:
            with open(self.QUEUE_FILE) as f:
                data = json.load(f)

            for d in data:
                job = JobListing(
                    id=d["id"],
                    title=d["title"],
                    company=d["company"],
                    location=d["location"],
                    url=d["url"],
                    description=d.get("description", ""),
                    salary=d.get("salary"),
                    date_posted=(
                        datetime.fromisoformat(d["date_posted"]) if d.get("date_posted") else None
                    ),
                    site=d["site"],
                    is_remote=d.get("is_remote", False),
                    job_type=d.get("job_type"),
                    score=d.get("score", 0.0),
                    status=d.get("status", "pending"),
                    applied_at=(
                        datetime.fromisoformat(d["applied_at"]) if d.get("applied_at") else None
                    ),
                    error=d.get("error"),
                )
                self._jobs[job.url] = job

            logger.info(f"Loaded {len(self._jobs)} jobs from queue")
        except Exception as e:
            logger.error(f"Failed to load queue: {e}")
