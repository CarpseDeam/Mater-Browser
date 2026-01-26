"""Dedicated success detection for application completion."""
import logging
from dataclasses import dataclass
from enum import Enum

from playwright.sync_api import Page

logger = logging.getLogger(__name__)


class CompletionSignal(Enum):
    """Type of completion signal detected."""
    URL_PATTERN = "url_pattern"
    TEXT_CONTENT = "text_content"
    FORM_DISAPPEARED = "form_disappeared"
    NONE = "none"


@dataclass
class CompletionResult:
    """Result of completion check."""
    is_complete: bool
    signal: CompletionSignal
    details: str


SUCCESS_URL_PATTERNS: list[str] = [
    "post-apply",
    "postApplyJobId",
    "/confirmation",
    "/thank",
    "/success",
    "/submitted",
    "/complete",
    "/applied",
    "application-submitted",
    "apply/success",
]

SUCCESS_TEXT_PATTERNS: list[str] = [
    "thank you for applying",
    "application submitted",
    "application received",
    "application was sent",
    "your application has been submitted",
    "we have received your application",
    "successfully submitted",
    "thanks for applying",
    "application complete",
    "you have applied",
]


class SuccessDetector:
    """Detects application completion through multiple signals."""

    def __init__(self, page: Page) -> None:
        self._page = page
        self._forms_filled = False

    def mark_form_filled(self) -> None:
        """Mark that a form has been filled during this application."""
        self._forms_filled = True

    def reset(self) -> None:
        """Reset state for a new application."""
        self._forms_filled = False

    def check(self) -> CompletionResult:
        """Check all completion signals. Returns on first match."""
        url_result = self._check_url()
        if url_result.is_complete:
            logger.info(f"SUCCESS via URL: {url_result.details}")
            return url_result

        text_result = self._check_text()
        if text_result.is_complete:
            logger.info(f"SUCCESS via text: {text_result.details}")
            return text_result

        form_result = self._check_form_disappeared()
        if form_result.is_complete:
            logger.info(f"SUCCESS via form check: {form_result.details}")
            return form_result

        return CompletionResult(False, CompletionSignal.NONE, "")

    def _check_url(self) -> CompletionResult:
        """Check URL for success patterns."""
        url = self._page.url.lower()
        for pattern in SUCCESS_URL_PATTERNS:
            if pattern.lower() in url:
                return CompletionResult(True, CompletionSignal.URL_PATTERN, f"URL contains '{pattern}'")
        return CompletionResult(False, CompletionSignal.NONE, "")

    def _check_text(self) -> CompletionResult:
        """Check page content for success text."""
        try:
            content = self._page.content().lower()
            for pattern in SUCCESS_TEXT_PATTERNS:
                if pattern in content:
                    return CompletionResult(True, CompletionSignal.TEXT_CONTENT, f"Page contains '{pattern}'")
        except Exception as e:
            logger.debug(f"Text check failed: {e}")
        return CompletionResult(False, CompletionSignal.NONE, "")

    def _check_form_disappeared(self) -> CompletionResult:
        """Check if form inputs have disappeared (submitted successfully)."""
        if not self._forms_filled:
            return CompletionResult(False, CompletionSignal.NONE, "")

        try:
            inputs = self._page.locator("input:not([type='hidden']), select, textarea").count()
            if inputs <= 2:
                url = self._page.url.lower()
                if "login" not in url and "signin" not in url and "register" not in url:
                    return CompletionResult(True, CompletionSignal.FORM_DISAPPEARED, f"Only {inputs} form inputs remain")
        except Exception as e:
            logger.debug(f"Form check failed: {e}")
        return CompletionResult(False, CompletionSignal.NONE, "")
