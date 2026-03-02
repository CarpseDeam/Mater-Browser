"""Job application agent - orchestrates LinkedIn Easy Apply flow."""
import logging

from ..browser.tabs import TabManager
from .models import ApplicationStatus, ApplicationResult, LINKEDIN_PATTERNS
from .linkedin_flow import LinkedInFlow

logger = logging.getLogger(__name__)


class ApplicationAgent:
    """
    Orchestrates LinkedIn Easy Apply flow.

    LinkedIn Easy Apply only - all other sources are skipped.
    """

    def __init__(
        self,
        tab_manager: TabManager,
        max_pages: int = 15,
    ) -> None:
        """
        Initialize the application agent.

        Args:
            tab_manager: TabManager for handling browser tabs.
            max_pages: Maximum pages to process before giving up.
        """
        self._tabs = tab_manager
        self._max_pages = max_pages

    def apply(self, job_url: str) -> ApplicationResult:
        """
        Apply to a LinkedIn Easy Apply job.

        Args:
            job_url: URL of the LinkedIn job posting.

        Returns:
            ApplicationResult with status and details.
        """
        logger.info(f"Starting application: {job_url}")

        if not self._is_linkedin(job_url):
            return ApplicationResult(
                status=ApplicationStatus.SKIPPED,
                message="Not a LinkedIn job - LinkedIn Easy Apply only",
                url=job_url,
            )

        try:
            page = self._tabs.get_page()
            flow = LinkedInFlow(
                page=page,
                tabs=self._tabs,
                max_pages=self._max_pages,
            )
            return flow.apply(job_url)

        except Exception as e:
            logger.exception(f"Application error: {e}")
            return ApplicationResult(
                status=ApplicationStatus.ERROR,
                message=str(e),
                url=job_url,
            )

    def _is_linkedin(self, url: str) -> bool:
        """Check if URL is a LinkedIn job."""
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in LINKEDIN_PATTERNS)
