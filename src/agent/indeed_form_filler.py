"""Deterministic form filler for Indeed Easy Apply."""
import logging

from playwright.sync_api import Page, Locator

from .answer_engine import AnswerEngine

logger = logging.getLogger(__name__)


class IndeedFormFiller:
    """Fill Indeed Easy Apply forms using config-driven answers."""

    CONTINUE_BUTTON_PATTERNS = [
        'button[data-testid="continueButton"]',
        'button[data-testid="submitButton"]',
        'button:has-text("Continue")',
        'button:has-text("Submit")',
        'button:has-text("Apply")',
        'button:has-text("Next")',
        '[type="submit"]',
    ]

    SUCCESS_PAGE_INDICATORS = [
        '[data-testid="ia-success"]',
        'text="Application submitted"',
        'text="Your application has been submitted"',
        '[class*="success"]',
        'h1:has-text("Application submitted")',
    ]

    REVIEW_PAGE_INDICATORS = [
        '[data-testid="review-page"]',
        'text="Review your application"',
        'h1:has-text("Review")',
        '[class*="review"]',
    ]

    def __init__(self, page: Page, answer_engine: AnswerEngine | None = None) -> None:
        self._page = page
        self._answers = answer_engine or AnswerEngine()
        self._unknown_questions: list[str] = []

    def fill_current_page(self) -> tuple[bool, list[str]]:
        """Fill all fields on the current page.

        Returns:
            (success, list of unknown questions)
        """
        self._unknown_questions = []

        self._fill_text_inputs()
        self._fill_number_inputs()
        self._fill_textareas()
        self._fill_selects()
        self._fill_radios()
        self._fill_checkboxes()

        return len(self._unknown_questions) == 0, self._unknown_questions

    def _fill_text_inputs(self) -> None:
        """Fill text input fields."""
        inputs = self._page.locator(
            'input[type="text"], input[type="email"], input[type="tel"], input:not([type])'
        ).all()

        for inp in inputs:
            self._fill_input(inp, "text")

    def _fill_number_inputs(self) -> None:
        """Fill number input fields."""
        inputs = self._page.locator('input[type="number"]').all()

        for inp in inputs:
            self._fill_input(inp, "number")

    def _fill_input(self, inp: Locator, field_type: str) -> None:
        """Fill a single input field."""
        try:
            if not inp.is_visible() or not inp.is_editable():
                return
        except Exception:
            return

        try:
            if inp.get_attribute("type") == "hidden":
                return
            if inp.is_disabled():
                return
        except Exception:
            pass

        try:
            current_value = inp.input_value()
            if current_value and len(current_value.strip()) > 0:
                return
        except Exception:
            pass

        question = self._get_question_text(inp)
        if not question:
            return

        answer = self._answers.get_answer(question, field_type)

        if answer is not None:
            try:
                inp.fill(str(answer))
                logger.info(f"Filled: {question[:40]} = {answer}")
            except Exception as e:
                logger.warning(f"Could not fill {question[:40]}: {e}")
        else:
            self._unknown_questions.append(question)

    def _fill_textareas(self) -> None:
        """Fill textarea fields (open-ended questions)."""
        textareas = self._page.locator(
            'textarea, [data-testid="rich-text-question-input"], .rich-text-question-input'
        ).all()

        for textarea in textareas:
            try:
                if not textarea.is_visible() or not textarea.is_editable():
                    continue
            except Exception:
                continue

            try:
                if textarea.is_disabled():
                    continue
            except Exception:
                pass

            try:
                current_value = textarea.input_value()
                if current_value and len(current_value.strip()) > 0:
                    continue
            except Exception:
                try:
                    current_text = textarea.text_content()
                    if current_text and len(current_text.strip()) > 0:
                        continue
                except Exception:
                    pass

            question = self._get_question_text(textarea)
            if not question:
                continue

            answer = self._answers.get_answer(question, "text")

            if answer is not None:
                try:
                    textarea.fill(str(answer))
                    logger.info(f"Filled textarea: {question[:40]} = {str(answer)[:50]}")
                except Exception as e:
                    logger.warning(f"Could not fill textarea {question[:40]}: {e}")
            else:
                self._unknown_questions.append(question)

    def _fill_selects(self) -> None:
        """Fill select dropdowns."""
        selects = self._page.locator('select').all()

        for select in selects:
            try:
                if not select.is_visible():
                    continue
            except Exception:
                continue

            try:
                if select.is_disabled():
                    continue
            except Exception:
                pass

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

    def _fill_radios(self) -> None:
        """Fill radio button groups."""
        fieldsets = self._page.locator('fieldset').all()

        for fieldset in fieldsets:
            try:
                if not fieldset.is_visible():
                    continue
            except Exception:
                continue

            question = self._get_fieldset_question(fieldset)
            if not question:
                continue

            radios = fieldset.locator('input[type="radio"]').all()
            if not radios:
                continue

            already_checked = any(
                r.is_checked() for r in radios
                if self._is_visible_and_enabled(r)
            )
            if already_checked:
                continue

            answer = self._answers.get_answer(question, "radio")
            if answer is None:
                self._unknown_questions.append(question)
                continue

            answer_str = str(answer).lower()

            for radio in radios:
                if not self._is_visible_and_enabled(radio):
                    continue

                label = self._get_radio_label(radio)
                if label and answer_str in label.lower():
                    try:
                        radio.check()
                        logger.info(f"Radio: {question[:40]} = {label}")
                    except Exception:
                        pass
                    break

    def _fill_checkboxes(self) -> None:
        """Fill checkboxes."""
        checkboxes = self._page.locator('input[type="checkbox"]').all()

        for cb in checkboxes:
            try:
                if not cb.is_visible():
                    continue
            except Exception:
                continue

            try:
                if cb.is_disabled():
                    continue
            except Exception:
                pass

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
            parent = element.locator('xpath=..').first
            if parent.count() > 0:
                prev_text = parent.locator('xpath=preceding-sibling::*[1]').first
                if prev_text.count() > 0:
                    text = prev_text.text_content()
                    if text:
                        return text.strip()
        except Exception:
            pass

        try:
            name = element.get_attribute("name")
            if name:
                return name.replace("_", " ").replace("-", " ").strip()
        except Exception:
            pass

        return ""

    def _get_fieldset_question(self, fieldset: Locator) -> str:
        """Extract question from fieldset legend or aria-label."""
        try:
            aria = fieldset.get_attribute("aria-label")
            if aria:
                return aria.strip()
        except Exception:
            pass

        try:
            legend = fieldset.locator('legend').first
            if legend.count() > 0:
                text = legend.text_content()
                if text:
                    return text.strip()
        except Exception:
            pass

        try:
            header = fieldset.locator('h1, h2, h3, h4, h5, h6, .question-text, [class*="question"]').first
            if header.count() > 0:
                text = header.text_content()
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

        try:
            value = radio.get_attribute("value")
            if value:
                return value.strip()
        except Exception:
            pass

        return ""

    def _is_visible_and_enabled(self, element: Locator) -> bool:
        """Check if element is visible and enabled."""
        try:
            if not element.is_visible():
                return False
            if element.is_disabled():
                return False
            return True
        except Exception:
            return False

    def click_continue(self) -> bool:
        """Click the Continue/Submit button."""
        for selector in self.CONTINUE_BUTTON_PATTERNS:
            try:
                btn = self._page.locator(selector).first
                if btn.is_visible(timeout=1000) and btn.is_enabled():
                    btn.click()
                    self._page.wait_for_timeout(500)
                    return True
            except Exception:
                continue
        return False

    def is_success_page(self) -> bool:
        """Check if on confirmation/success page."""
        for indicator in self.SUCCESS_PAGE_INDICATORS:
            try:
                if self._page.locator(indicator).first.is_visible(timeout=500):
                    return True
            except Exception:
                continue
        return False

    def is_review_page(self) -> bool:
        """Check if on review page before submit."""
        for indicator in self.REVIEW_PAGE_INDICATORS:
            try:
                if self._page.locator(indicator).first.is_visible(timeout=500):
                    return True
            except Exception:
                continue
        return False
