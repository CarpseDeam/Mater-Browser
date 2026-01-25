"""JobSpy wrapper for multi-platform job scraping."""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from jobspy import scrape_jobs

logger = logging.getLogger(__name__)


@dataclass
class JobListing:
    """Represents a scraped job."""

    id: str
    title: str
    company: str
    location: str
    url: str
    description: str
    salary: Optional[str]
    date_posted: Optional[datetime]
    site: str
    is_remote: bool
    job_type: Optional[str]

    score: float = 0.0
    status: str = "pending"
    applied_at: Optional[datetime] = None
    error: Optional[str] = None


class JobSpyClient:
    """Client for scraping jobs via JobSpy."""

    def __init__(
        self,
        sites: Optional[list[str]] = None,
        results_wanted: int = 50,
        hours_old: int = 72,
        country: str = "USA",
    ) -> None:
        self.sites = sites or ["linkedin", "indeed", "glassdoor"]
        self.results_wanted = results_wanted
        self.hours_old = hours_old
        self.country = country

    def search(
        self,
        search_term: str,
        location: str = "remote",
        remote_only: bool = True,
        job_type: Optional[str] = None,
    ) -> list[JobListing]:
        """
        Search for jobs matching criteria.

        Args:
            search_term: Job title/keywords (e.g., "Python Engineer")
            location: Location filter
            remote_only: Only return remote jobs
            job_type: Filter by job type (fulltime, parttime, contract)

        Returns:
            List of JobListing objects
        """
        logger.info(f"Searching: '{search_term}' in {location}")
        logger.info(f"Sites: {self.sites}, Max results: {self.results_wanted}")

        try:
            df = scrape_jobs(
                site_name=self.sites,
                search_term=search_term,
                location=location,
                results_wanted=self.results_wanted,
                hours_old=self.hours_old,
                country_indeed=self.country,
                is_remote=remote_only,
                job_type=job_type,
            )

            if df is None or df.empty:
                logger.warning("No jobs found")
                return []

            jobs = []
            for _, row in df.iterrows():
                job = JobListing(
                    id=str(row.get("id", "")),
                    title=str(row.get("title", "")),
                    company=str(row.get("company", "")),
                    location=str(row.get("location", "")),
                    url=str(row.get("job_url", "")),
                    description=str(row.get("description", "")),
                    salary=str(row.get("salary", "")) if row.get("salary") else None,
                    date_posted=row.get("date_posted"),
                    site=str(row.get("site", "")),
                    is_remote=bool(row.get("is_remote", False)),
                    job_type=str(row.get("job_type", "")) if row.get("job_type") else None,
                )
                jobs.append(job)

            logger.info(f"Found {len(jobs)} jobs")
            return jobs

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
