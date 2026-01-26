"""Navigation and completion detection helpers for form processing."""
import logging
import re

from ..browser.page import Page
from ..extractor.dom_service import DomState

logger = logging.getLogger(__name__)


def click_next_button(page: Page) -> bool:
    """Try to click Next/Continue/Submit button using semantic locators."""
    raw = page.raw

    next_locator = (
        raw.get_by_role("button", name=re.compile(r"next|continue|submit|review", re.IGNORECASE))
        .or_(raw.get_by_role("link", name=re.compile(r"next|continue", re.IGNORECASE)))
        .or_(raw.locator('[type="submit"]'))
        .or_(raw.locator('[aria-label*="Next" i]'))
        .or_(raw.locator('[aria-label*="Continue" i]'))
        .or_(raw.locator('[aria-label*="Submit" i]'))
        .or_(raw.locator('[data-testid*="next" i]'))
        .or_(raw.locator('[data-testid*="submit" i]'))
    )

    try:
        first_match = next_locator.first
        if first_match.is_visible(timeout=3000):
            try:
                tag = first_match.evaluate("el => el.tagName")
                text = first_match.evaluate("el => el.textContent?.trim()?.substring(0, 30)")
                logger.info(f"Found Next button: <{tag}> '{text}'")
            except Exception:
                logger.info("Found Next button (details unavailable)")

            first_match.click()
            page.wait(1500)
            logger.info("Clicked Next button successfully")
            return True
    except Exception as e:
        logger.debug(f"Next button locator failed: {e}")

    return False


def is_complete(page: Page, pages_processed: int = 0) -> bool:
    """Check if application was submitted using semantic locators."""
    if pages_processed < 2:
        return False

    raw = page.raw
    current_url = page.url.lower()

    negative_signals = ["/job/", "/jobs/", "/careers/", "/viewjob", "/job-detail", "/apply", "linkedin.com/jobs/view"]
    if any(sig in current_url for sig in negative_signals):
        if not any(pos in current_url for pos in ["success", "submitted", "confirmed", "thank", "complete"]):
            return False

    completion_locator = (
        raw.get_by_text(re.compile(r"application submitted|thank you for applying|successfully submitted|application received", re.IGNORECASE))
        .or_(raw.locator('[data-test="application-complete"]'))
        .or_(raw.locator('[data-testid*="success" i]'))
        .or_(raw.locator('[data-testid*="complete" i]'))
        .or_(raw.locator('.application-complete'))
        .or_(raw.locator('#application-success'))
        .or_(raw.locator('[class*="success"][class*="message" i]'))
    )

    try:
        if completion_locator.first.is_visible(timeout=1000):
            logger.info("Completion indicator found via locator")
            return True
    except Exception:
        pass

    try:
        content = raw.content().lower()
        completion_phrases = [
            "thank you for applying",
            "application submitted",
            "application received",
            "we have received your application",
            "your application has been submitted",
        ]
        if any(phrase in content for phrase in completion_phrases):
            logger.info("Completion detected via page content")
            return True
    except Exception:
        pass

    return False


def try_resume_upload(page: Page, dom_state: DomState, resume_path: str | None, dom_service) -> bool:
    """Try to upload resume if file input found."""
    if not resume_path:
        return False

    for el in dom_state.elements:
        if el.tag == "input" and el.type == "file":
            label = (el.label or "").lower()
            name = (el.name or "").lower()

            if any(kw in label or kw in name for kw in ["resume", "cv", "upload"]):
                selector = dom_service.get_selector(el.ref)
                if selector:
                    try:
                        page.raw.locator(selector).set_input_files(resume_path)
                        logger.info(f"Uploaded resume to {el.ref}")
                        page.wait(1000)
                        return True
                    except Exception as e:
                        logger.warning(f"Resume upload failed: {e}")
    return False
