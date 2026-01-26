"""Registry of ATS handlers."""
import logging
from typing import Optional, Type

from playwright.sync_api import Page

from .detector import ATSType, ATSDetector
from .base_handler import BaseATSHandler
from .handlers import (
    WorkdayHandler,
    GreenhouseHandler,
    LeverHandler,
    ICIMSHandler,
    PhenomHandler,
    SmartRecruitersHandler,
)

logger = logging.getLogger(__name__)


HANDLER_REGISTRY: dict[ATSType, Type[BaseATSHandler]] = {
    ATSType.WORKDAY: WorkdayHandler,
    ATSType.GREENHOUSE: GreenhouseHandler,
    ATSType.LEVER: LeverHandler,
    ATSType.ICIMS: ICIMSHandler,
    ATSType.PHENOM: PhenomHandler,
    ATSType.SMARTRECRUITERS: SmartRecruitersHandler,
}


def get_handler(
    page: Page,
    profile: dict,
    resume_path: Optional[str] = None,
) -> Optional[BaseATSHandler]:
    """Get the appropriate handler for the current page."""
    detector = ATSDetector(page)
    ats_type = detector.detect()

    if ats_type == ATSType.UNKNOWN:
        logger.info("No ATS handler available - will use Claude fallback")
        return None

    handler_class = HANDLER_REGISTRY.get(ats_type)
    if handler_class:
        logger.info(f"Using {ats_type.value} handler")
        return handler_class(page, profile, resume_path)

    return None
