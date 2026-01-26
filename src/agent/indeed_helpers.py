"""Indeed-specific helpers for resume handling and modal dismissal."""
import logging
import re

from ..browser.page import Page
from ..extractor.dom_service import DomState

logger = logging.getLogger(__name__)


class IndeedHelpers:
    """Handles Indeed-specific UI elements: resume cards, modals, continue buttons."""

    def __init__(self, page: Page) -> None:
        self._page = page

    def try_resume_upload(self, dom_state: DomState, resume_path: str | None, dom_service) -> bool:
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
                            self._page.raw.locator(selector).set_input_files(resume_path)
                            logger.info(f"Uploaded resume to {el.ref}")
                            self._page.wait(1000)
                            return True
                        except Exception as e:
                            logger.warning(f"Resume upload failed: {e}")
        return False

    def handle_resume_card(self) -> bool:
        """
        Handle Indeed's resume selection page.

        Indeed shows resume options as cards with hidden radio inputs.
        If a resume is already selected, we skip clicking and just advance.

        Returns:
            True if on resume page and handled, False if not on Indeed resume page.
        """
        page = self._page.raw
        current_url = self._page.url.lower()

        if "indeed.com" not in current_url:
            return False

        if "resume" not in current_url and "resume" not in page.content().lower()[:2000]:
            return False

        has_cards = (
            page.locator('[data-testid*="resume-selection"]').count() > 0 or
            page.locator('[data-testid*="resume"][data-testid*="card"]').count() > 0 or
            page.locator('[class*="resume-card"]').count() > 0 or
            "resume" in current_url
        )
        if not has_cards:
            return False

        logger.info("Checking for Indeed resume selection page...")

        if self._is_resume_selected(page):
            logger.info("Resume already selected - skipping card click")
            return self._click_continue()

        logger.info("No resume selected - looking for Indeed resume card to click...")

        resume_card = self._find_resume_card(page)
        if resume_card:
            try:
                logger.info("Found Indeed resume card, clicking...")
                resume_card.click(force=True)
                self._page.wait(1000)
                return self._click_continue()
            except Exception as e:
                logger.debug(f"Indeed resume card click failed: {e}")

        return False

    def _is_resume_selected(self, page) -> bool:
        """Check if a resume card is already selected on Indeed."""
        selected_locator = (
            page.locator('[data-testid*="resume"][aria-checked="true"]').locator('visible=true')
            .or_(page.locator('[data-testid*="resume"]:has(input[aria-checked="true"])').locator('visible=true'))
            .or_(page.locator('[data-testid*="resume"]:has(input:checked)').locator('visible=true'))
            .or_(page.locator('[aria-checked="true"][data-testid*="card"]').locator('visible=true'))
            .or_(page.locator('.ia-Resume-selectedIcon').locator('visible=true'))
            .or_(page.locator('[class*="selected"][class*="resume"]').locator('visible=true'))
        )

        try:
            return selected_locator.first.is_visible(timeout=2000)
        except Exception:
            return False

    def _find_resume_card(self, page):
        """Find the visible Indeed Resume card container to click."""
        resume_card_locator = (
            page.locator('[data-testid*="structured-resume"][data-testid*="card"]').locator('visible=true')
            .or_(page.locator('[data-testid*="resume-selection"][data-testid*="card"]').locator('visible=true'))
            .or_(page.locator('div:has-text("Indeed Resume")').locator('visible=true').first)
            .or_(page.locator('label:has-text("Indeed Resume")').locator('visible=true'))
        )

        try:
            count = resume_card_locator.count()
            if count == 0:
                return None

            for i in range(count):
                card = resume_card_locator.nth(i)
                try:
                    if not card.is_visible(timeout=500):
                        continue
                    text = (card.text_content() or "").lower()
                    if "indeed resume" in text and "upload" not in text:
                        return card
                except Exception:
                    continue

            first_visible = resume_card_locator.first
            if first_visible.is_visible(timeout=500):
                return first_visible
        except Exception:
            pass

        return None

    def _click_continue(self) -> bool:
        """Click Indeed's Continue/Next button on resume page."""
        page = self._page.raw

        logger.info("Looking for Indeed Continue button...")

        indeed_continue_locator = (
            page.locator('[data-testid="ia-continueButton"]')
            .or_(page.locator('[data-testid*="continue" i]'))
            .or_(page.locator('[data-tn-element="continueButton"]'))
            .or_(page.get_by_role("button", name=re.compile(r"^continue$", re.IGNORECASE)))
            .or_(page.get_by_role("button", name=re.compile(r"continue to", re.IGNORECASE)))
            .or_(page.locator('.ia-continueButton'))
            .or_(page.locator('[class*="ia-"][class*="continue" i]'))
            .or_(page.locator('[class*="continue"][class*="button" i]'))
            .or_(page.locator('button:has-text("Continue")'))
            .or_(page.locator('[type="submit"]'))
        )

        try:
            first_match = indeed_continue_locator.first
            if first_match.is_visible(timeout=2000):
                try:
                    text = first_match.evaluate("el => el.textContent?.trim()?.substring(0, 30)")
                    logger.info(f"Found Indeed Continue button: '{text}'")
                except Exception:
                    pass

                first_match.click()
                logger.info("Clicked Indeed Continue button successfully")
                self._page.wait(1500)
                return True
        except Exception as e:
            logger.debug(f"Continue button not immediately visible: {e}")

        logger.info("Scrolling to find Continue button...")
        try:
            page.evaluate("window.scrollBy(0, 500)")
            self._page.wait(500)

            first_match = indeed_continue_locator.first
            if first_match.is_visible(timeout=2000):
                first_match.scroll_into_view_if_needed()
                first_match.click()
                logger.info("Clicked Indeed Continue button after scroll")
                self._page.wait(1500)
                return True
        except Exception as e:
            logger.debug(f"Continue button not found after scroll: {e}")

        return False

    def dismiss_modal(self) -> bool:
        """Check for and dismiss Indeed confirmation modals."""
        page = self._page.raw

        modal_dismiss_locator = (
            page.get_by_role("button", name=re.compile(r"continue applying", re.IGNORECASE))
            .or_(page.get_by_role("button", name=re.compile(r"continue", re.IGNORECASE)))
            .or_(page.locator('[data-testid*="continue"]'))
            .or_(page.locator('button:has-text("Continue Applying")'))
            .or_(page.locator('[role="dialog"] button:has-text("Continue")'))
            .or_(page.locator('.modal button:has-text("Continue")'))
        )

        try:
            button = modal_dismiss_locator.first
            if button.is_visible(timeout=1000):
                logger.info("Indeed modal detected - clicking Continue")
                button.click()
                self._page.wait(1000)
                return True
        except Exception:
            pass

        return False
