#!/usr/bin/env python
"""Apply to a job - simple CLI entry point.

Usage:
    python apply.py <job_url>
    python apply.py https://www.linkedin.com/jobs/view/123456789
"""
import sys
import logging
from pathlib import Path

from src.core.logging import setup_logging
from src.core.config import Settings
from src.browser.connection import BrowserConnection
from src.browser.tabs import TabManager
from src.profile.manager import load_profile
from src.workflow.application import ApplicationWorkflow

logger = logging.getLogger(__name__)


def main() -> int:
    """Run job application."""
    setup_logging("INFO")

    if len(sys.argv) < 2:
        print("Usage: python apply.py <job_url>")
        print("Example: python apply.py https://linkedin.com/jobs/view/123456")
        return 1

    url = sys.argv[1]
    logger.info("=== Mater-Browser: Applying to Job ===")
    logger.info(f"URL: {url}")

    settings = Settings.from_yaml(Path("config/settings.yaml"))
    profile_data = load_profile(Path("config/profile.yaml"))
    profile = profile_data.model_dump()

    resume_path = profile.get("resume_path")
    if resume_path and not Path(resume_path).exists():
        logger.warning(f"Resume not found at {resume_path}")
        resume_path = None

    connection = BrowserConnection(
        cdp_port=settings.browser.cdp_port,
        max_retries=settings.browser.connect_retries,
        retry_delay=settings.browser.retry_delay,
    )

    if not connection.connect():
        logger.error("Failed to connect to Chrome. Run scripts/start_chrome.bat first.")
        return 1

    try:
        tabs = TabManager(connection.browser)
        page = tabs.get_page()

        workflow = ApplicationWorkflow(
            page=page,
            profile=profile,
            resume_path=resume_path,
            max_pages=15,
        )

        result = workflow.run(url)

        if result.success:
            logger.info(f"SUCCESS: {result.reason}")
            logger.info(f"Pages processed: {result.pages_processed}")
            return 0
        else:
            logger.error(f"FAILED: {result.reason}")
            logger.error(f"Pages processed: {result.pages_processed}")
            return 1

    finally:
        connection.disconnect()


if __name__ == "__main__":
    sys.exit(main())
