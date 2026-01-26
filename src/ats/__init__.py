"""ATS detection and handling system."""
from .detector import ATSType, ATSDetector
from .registry import get_handler
from .base_handler import BaseATSHandler, FormPage, PageResult

__all__ = [
    "ATSType",
    "ATSDetector",
    "get_handler",
    "BaseATSHandler",
    "FormPage",
    "PageResult",
]
