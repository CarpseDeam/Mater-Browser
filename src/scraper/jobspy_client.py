"""JobSpy wrapper for multi-platform job scraping."""
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import pandas as pd
from jobspy import scrape_jobs

logger = logging.getLogger(__name__)


def _safe_str(value, default: str = "") -> str:
    """Safely convert value to string, handling None/NaN."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value)


def _safe_bool(value, default: bool = False) -> bool:
    """Safely convert value to bool, handling None/NaN."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return bool(value)


def _safe_date(value) -> Optional[datetime]:
    """Safely convert date/datetime, handling None/NaN."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return None


def _extract_location(value) -> str:
    """Extract location string from JobSpy location field.
    
    JobSpy can return a Location object with city/state/country attributes,
    or just a string.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    
    # If it's already a string
    if isinstance(value, str):
        return value
    
    # If it's a Location object with attributes
    parts = []
    if hasattr(value, 'city') and value.city:
        parts.append(str(value.city))
    if hasattr(value, 'state') and value.state:
        parts.append(str(value.state))
    if hasattr(value, 'country') and value.country and not parts:
        parts.append(str(value.country))
    
    if parts:
        return ", ".join(parts)
    
    # Fallback: try to convert to string
    return str(value) if value else ""


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
        self.sites = sites or ["indeed", "linkedin"]  # Glassdoor often fails
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
                try:
                    job = JobListing(
                        id=_safe_str(row.get("id"), default=f"job_{len(jobs)}"),
                        title=_safe_str(row.get("title"), default="Unknown Title"),
                        company=_safe_str(row.get("company"), default="Unknown Company"),
                        location=_extract_location(row.get("location")),
                        url=_safe_str(row.get("job_url")),
                        description=_safe_str(row.get("description")),
                        salary=_safe_str(row.get("salary")) or None,
                        date_posted=_safe_date(row.get("date_posted")),
                        site=_safe_str(row.get("site")),
                        is_remote=_safe_bool(row.get("is_remote")),
                        job_type=_safe_str(row.get("job_type")) or None,
                    )
                    
                    # Skip jobs without URLs
                    if not job.url:
                        logger.debug(f"Skipping job without URL: {job.title}")
                        continue
                        
                    jobs.append(job)
                except Exception as e:
                    logger.warning(f"Failed to parse job row: {e}")
                    continue

            logger.info(f"Found {len(jobs)} valid jobs")
            return jobs

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
