"""CLI entry point for Mater-Browser job application agent."""
import argparse
import logging
import sys
from pathlib import Path

from src.core.logging import setup_logging
from src.core.config import Settings
from src.browser.connection import BrowserConnection
from src.browser.tabs import TabManager
from src.agent.application import ApplicationAgent, ApplicationStatus
from src.profile.manager import load_profile


def main() -> int:
    """Run job application agent."""
    parser = argparse.ArgumentParser(
        description="Apply to a job using AI-powered browser automation"
    )
    parser.add_argument(
        "url",
        help="URL of the job posting to apply to"
    )
    parser.add_argument(
        "--profile", "-p",
        default="config/profile.yaml",
        help="Path to profile YAML file"
    )
    parser.add_argument(
        "--resume", "-r",
        help="Path to resume PDF (overrides profile setting)"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--highlight",
        action="store_true",
        help="Highlight detected elements (for debugging)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract and plan but don't execute"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=15,
        help="Maximum pages to process (default: 15)"
    )

    args = parser.parse_args()

    level = "DEBUG" if args.debug else "INFO"
    setup_logging(level)
    logger = logging.getLogger(__name__)

    logger.info("=== Mater-Browser Job Application Agent ===")
    logger.info(f"Target: {args.url}")

    settings = Settings.from_yaml(Path("config/settings.yaml"))
    profile_data = load_profile(Path(args.profile))
    profile = profile_data.model_dump()

    resume_path = args.resume or profile.get("resume_path")
    if resume_path:
        if Path(resume_path).exists():
            logger.info(f"Resume: {resume_path}")
        else:
            logger.warning(f"Resume not found: {resume_path}")
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

        agent = ApplicationAgent(
            tab_manager=tabs,
            profile=profile,
            resume_path=resume_path,
            max_pages=args.max_pages,
            claude_model=settings.claude.model,
        )

        result = agent.apply(args.url)

        logger.info("=" * 50)
        logger.info(f"Status: {result.status.value}")
        logger.info(f"Message: {result.message}")
        logger.info(f"Pages processed: {result.pages_processed}")

        if result.status == ApplicationStatus.SUCCESS:
            logger.info("Application submitted successfully!")
            return 0
        else:
            logger.warning(f"Application {result.status.value}: {result.message}")
            return 1

    finally:
        connection.disconnect()


if __name__ == "__main__":
    sys.exit(main())
