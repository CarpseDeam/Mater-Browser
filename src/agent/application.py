"""Job application agent - orchestrates the full application flow."""
import logging
from typing import Optional

from ..browser.tabs import TabManager
from .claude import ClaudeAgent
from .models import (
    JobSource,
    ApplicationStatus,
    ApplicationResult,
    LINKEDIN_PATTERNS,
    INDEED_PATTERNS,
    APPLICATION_TIMEOUT_SECONDS,
)
from .linkedin_flow import LinkedInFlow
from .external_flow import ExternalFlow

logger = logging.getLogger(__name__)


class ApplicationAgent:
    """
    Orchestrates complete job application flow.

    Handles:
    - Finding and clicking Apply button
    - Following external ATS links (new tabs)
    - Multi-page form navigation
    - Resume upload
    - Submit detection
    """

    def __init__(
        self,
        tab_manager: TabManager,
        profile: dict,
        resume_path: Optional[str] = None,
        max_pages: int = 15,
        claude_model: str = "claude-sonnet-4-20250514",
        timeout_seconds: float = APPLICATION_TIMEOUT_SECONDS,
    ) -> None:
        """
        Initialize the application agent.

        Args:
            tab_manager: TabManager for handling browser tabs.
            profile: User profile dictionary with application data.
            resume_path: Optional path to resume PDF file.
            max_pages: Maximum pages to process before giving up.
            claude_model: Claude model to use for form analysis.
            timeout_seconds: Maximum seconds for entire application attempt.
        """
        self._tabs = tab_manager
        self._profile = profile
        self._resume_path = resume_path
        self._max_pages = max_pages
        self._timeout_seconds = timeout_seconds
        self._claude = ClaudeAgent(model=claude_model)

    def apply(self, job_url: str) -> ApplicationResult:
        """
        Apply to a job given its URL.

        Routes to source-specific apply logic based on URL.

        Args:
            job_url: URL of the job posting (LinkedIn, Indeed, company site, etc.)

        Returns:
            ApplicationResult with status and details.
        """
        logger.info(f"Starting application: {job_url}")

        source = self._detect_source(job_url)
        logger.info(f"Detected source: {source.value}")

        try:
            page = self._tabs.get_page()

            if source == JobSource.LINKEDIN:
                flow = LinkedInFlow(
                    page=page,
                    tabs=self._tabs,
                    claude=self._claude,
                    profile=self._profile,
                    resume_path=self._resume_path,
                    timeout_seconds=self._timeout_seconds,
                    max_pages=self._max_pages,
                )
                return flow.apply(job_url)
            else:
                flow = ExternalFlow(
                    page=page,
                    tabs=self._tabs,
                    claude=self._claude,
                    profile=self._profile,
                    resume_path=self._resume_path,
                    timeout_seconds=self._timeout_seconds,
                    max_pages=self._max_pages,
                )
                return flow.apply(job_url, source)

        except Exception as e:
            logger.exception(f"Application error: {e}")
            return ApplicationResult(
                status=ApplicationStatus.ERROR,
                message=str(e),
                url=job_url
            )

    def _detect_source(self, url: str) -> JobSource:
        """
        Detect job source platform from URL.

        Args:
            url: Job posting URL.

        Returns:
            JobSource enum value for the detected platform.
        """
        url_lower = url.lower()

        if any(pattern in url_lower for pattern in LINKEDIN_PATTERNS):
            return JobSource.LINKEDIN
        elif any(pattern in url_lower for pattern in INDEED_PATTERNS):
            return JobSource.INDEED
        else:
            return JobSource.DIRECT
