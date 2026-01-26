"""Deterministic form filler for LinkedIn Easy Apply."""
import logging

from playwright.sync_api import Page, Locator

from .answer_engine import AnswerEngine

logger = logging.getLogger(__name__)


class LinkedInFormFiller:
    """Fill LinkedIn Easy Apply forms using config-driven answers."""

    SUBMIT_BUTTON_PATTERNS = [
        'button[aria-label*="Submit" i]',
        'button[aria-label*="Review" i]',
        'button[aria-label*="Next" i]',
        'button:has-text("Submit application")',
        'button:has-text("Review")',
        'button:has-text("Next")',
        'button:has-text("Continue")',
    ]

    def __init__(self, page: Page, answer_engine: AnswerEngine | None = None) -> None:
        self._page = page
        self._answers = answer_engine or AnswerEngine()
        self._unknown_questions: list[str] = []

    def fill_current_modal(self) -> tuple[bool, list[str]]:
        """Fill all fields in the current Easy Apply modal.

        Returns:
            (success, list of unknown questions)
        """
        self._unknown_questions = []

        modal = self._page.locator('.jobs-easy-apply-modal, [data-test-modal]').first
        try:
            if not modal.is_visible(timeout=2000):
                logger.warning("No Easy Apply modal found")
                return False, []
        except Exception:
            logger.warning("No Easy Apply modal found")
            return False, []

        self._fill_text_inputs(modal)
        self._fill_selects(modal)
        self._fill_radios(modal)
        self._fill_checkboxes(modal)

        return len(self._unknown_questions) == 0, self._unknown_questions

    def _fill_text_inputs(self, container: Locator) -> None:
        """Fill text input fields."""
        inputs = container.locator(
            'input[type="text"], input[type="email"], input[type="tel"], '
            'input[type="number"], input:not([type])'
        ).all()

        for inp in inputs:
            try:
                if not inp.is_visible() or not inp.is_editable():
                    continue
            except Exception:
                continue

            current_value = inp.input_value()
            if current_value and len(current_value) > 0:
                continue

            question = self._get_question_text(inp)
            if not question:
                continue

            field_type = inp.get_attribute("type") or "text"
            answer = self._answers.get_answer(question, field_type)

            if answer is not None:
                inp.fill(str(answer))
                logger.info(f"Filled: {question[:40]} = {answer}")
            else:
                self._unknown_questions.append(question)

    def _fill_selects(self, container: Locator) -> None:
        """Fill select dropdowns."""
        selects = container.locator('select').all()

        for select in selects:
            try:
                if not select.is_visible():
                    continue
            except Exception:
                continue

            question = self._get_question_text(select)
            if not question:
                continue

            answer = self._answers.get_answer(question, "select")
            if answer is not None:
                try:
                    select.select_option(label=str(answer))
                    logger.info(f"Selected: {question[:40]} = {answer}")
                except Exception:
                    try:
                        select.select_option(value=str(answer))
                    except Exception as e:
                        logger.warning(f"Could not select {answer} for {question}: {e}")
            else:
                self._unknown_questions.append(question)

    def _fill_radios(self, container: Locator) -> None:
        """Fill radio button groups."""
        fieldsets = container.locator('fieldset').all()

        for fieldset in fieldsets:
            try:
                if not fieldset.is_visible():
                    continue
            except Exception:
                continue

            legend = fieldset.locator('legend').first
            try:
                question = legend.text_content() if legend.count() > 0 else ""
            except Exception:
                question = ""
            if not question:
                continue

            answer = self._answers.get_answer(question, "radio")
            if answer is None:
                self._unknown_questions.append(question)
                continue

            answer_str = str(answer).lower()
            radios = fieldset.locator('input[type="radio"]').all()

            for radio in radios:
                label = self._get_radio_label(radio)
                if label and answer_str in label.lower():
                    try:
                        if not radio.is_checked():
                            radio.check()
                            logger.info(f"Radio: {question[:40]} = {label}")
                    except Exception:
                        pass
                    break

    def _fill_checkboxes(self, container: Locator) -> None:
        """Fill checkboxes."""
        checkboxes = container.locator('input[type="checkbox"]').all()

        for cb in checkboxes:
            try:
                if not cb.is_visible():
                    continue
            except Exception:
                continue

            question = self._get_question_text(cb)
            if not question:
                continue

            answer = self._answers.get_answer(question, "checkbox")
            if answer is not None:
                should_check = bool(answer)
                try:
                    if cb.is_checked() != should_check:
                        if should_check:
                            cb.check()
                        else:
                            cb.uncheck()
                        logger.info(f"Checkbox: {question[:40]} = {should_check}")
                except Exception:
                    pass

    def _get_question_text(self, element: Locator) -> str:
        """Extract question text from element's label, aria-label, or placeholder."""
        try:
            aria = element.get_attribute("aria-label")
            if aria:
                return aria.strip()
        except Exception:
            pass

        try:
            elem_id = element.get_attribute("id")
            if elem_id:
                label = self._page.locator(f'label[for="{elem_id}"]').first
                if label.count() > 0:
                    text = label.text_content()
                    if text:
                        return text.strip()
        except Exception:
            pass

        try:
            parent_label = element.locator('xpath=ancestor::label').first
            if parent_label.count() > 0:
                text = parent_label.text_content()
                if text:
                    return text.strip()
        except Exception:
            pass

        try:
            placeholder = element.get_attribute("placeholder")
            if placeholder:
                return placeholder.strip()
        except Exception:
            pass

        try:
            prev_label = element.locator('xpath=preceding-sibling::label[1]').first
            if prev_label.count() > 0:
                text = prev_label.text_content()
                if text:
                    return text.strip()
        except Exception:
            pass

        return ""

    def _get_radio_label(self, radio: Locator) -> str:
        """Get label text for a radio button."""
        try:
            radio_id = radio.get_attribute("id")
            if radio_id:
                label = self._page.locator(f'label[for="{radio_id}"]').first
                if label.count() > 0:
                    text = label.text_content()
                    if text:
                        return text.strip()
        except Exception:
            pass

        try:
            parent = radio.locator('xpath=ancestor::label').first
            if parent.count() > 0:
                text = parent.text_content()
                if text:
                    return text.strip()
        except Exception:
            pass

        return ""

    def click_next(self) -> bool:
        """Click the next/submit/review button."""
        for selector in self.SUBMIT_BUTTON_PATTERNS:
            try:
                btn = self._page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    self._page.wait_for_timeout(500)
                    return True
            except Exception:
                continue
        return False

    def is_confirmation_page(self) -> bool:
        """Check if we're on the confirmation/success page."""
        indicators = [
            'text="Application sent"',
            'text="Your application was sent"',
            '[data-test-modal-close-btn]',
            '.artdeco-modal__header:has-text("Application sent")',
        ]
        for indicator in indicators:
            try:
                if self._page.locator(indicator).first.is_visible(timeout=500):
                    return True
            except Exception:
                continue
        return False

    def close_modal(self) -> None:
        """Close the Easy Apply modal."""
        try:
            close_btn = self._page.locator(
                '[data-test-modal-close-btn], button[aria-label="Dismiss"]'
            ).first
            if close_btn.is_visible(timeout=1000):
                close_btn.click()
        except Exception:
            pass
