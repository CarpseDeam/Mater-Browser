"""Mater-Browser: LinkedIn Easy Apply automation."""
import logging
from pathlib import Path

from src.core.logging import setup_logging
from src.core.config import Settings
from src.browser.connection import BrowserConnection
from src.browser.tabs import TabManager
from src.profile.manager import load_profile
from src.agent.application import ApplicationAgent, ApplicationStatus

logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point - interactive mode."""
    setup_logging("INFO")
    logger.info("=== Mater-Browser Starting ===")

    settings = Settings.from_yaml(Path("config/settings.yaml"))
    profile_data = load_profile(Path("config/profile.yaml"))
    profile = profile_data.model_dump()

    resume_path = profile.get("resume_path")
    if resume_path and not Path(resume_path).exists():
        logger.warning(f"Resume not found: {resume_path}")
        resume_path = None

    connection = BrowserConnection(
        cdp_port=settings.browser.cdp_port,
        max_retries=settings.browser.connect_retries,
        retry_delay=settings.browser.retry_delay,
    )

    if not connection.connect():
        logger.error("Failed to connect. Run scripts/start_chrome.bat first.")
        return

    try:
        tabs = TabManager(connection.browser)
        page = tabs.get_page()

        agent = ApplicationAgent(
            tab_manager=tabs,
            max_pages=15,
        )

        print("\n" + "=" * 50)
        print("Mater-Browser Ready - LinkedIn Easy Apply Only")
        print("=" * 50)
        print("\nCommands:")
        print("  apply <url>  - Apply to a LinkedIn job")
        print("  quit         - Exit")
        print()

        while True:
            try:
                cmd = input("mater> ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not cmd:
                continue

            parts = cmd.split(maxsplit=1)
            command = parts[0].lower()

            if command in ("quit", "exit"):
                break

            elif command == "apply":
                if len(parts) < 2:
                    print("Usage: apply <job_url>")
                    continue

                url = parts[1]
                result = agent.apply(url)

                print("\n" + "=" * 50)
                print(f"Status: {result.status.value}")
                print(f"Message: {result.message}")
                print(f"Pages processed: {result.pages_processed}")

                if result.status == ApplicationStatus.SUCCESS:
                    print("Application submitted successfully!")
                else:
                    print(f"Application {result.status.value}")

            else:
                print(f"Unknown command: {command}")

    finally:
        connection.disconnect()

    logger.info("=== Mater-Browser Stopped ===")


if __name__ == "__main__":
    main()
