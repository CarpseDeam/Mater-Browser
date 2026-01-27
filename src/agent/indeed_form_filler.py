"""Deterministic form filler for Indeed Easy Apply."""
import logging
import re

from playwright.sync_api import Page, Locator

from .answer_engine import AnswerEngine

logger = logging.getLogger(__name__)


class IndeedFormFiller:
    """Fill Indeed Easy Apply forms using config-driven answers."""

    CONTINUE_PATTERNS = [
        '[data-testid="ia-continueButton"]',
        '[data-testid*="continue" i]',
        '[data-testid*="hp-continue-button"]',
        'button:has-text("Continue")',
        'button:has-text("Submit")',
        'button:has-text("Apply")',
        'button:has-text("Review")',
        'button[type="submit"]',
        '.ia-continueButton',
    ]

    SUBMIT_PATTERNS = [
        '[data-testid="ia-submitButton"]',
        '[data-testid*="submit"]',
        '[data-tn-element="submit"]',
        'button:has-text("Submit your application")',
        'button:has-text("Submit application")',
        'button:has-text("Submit")',
        'button[type="submit"]',
    ]

    SUCCESS_INDICATORS = [
        'text="Application submitted"',
        'text="Your application has been submitted"',
        'text="Thank you for applying"',
        'text="Successfully applied"',
        '[data-testid*="confirmation"]',
        '[data-testid*="success"]',
    ]

    def __init__(self, page: Page, answer_engine: AnswerEngine | None = None) -> None:
        self._page = page
        self._answers = answer_engine or AnswerEngine()
        self._unknown_questions: list[str] = []

    def fill_current_page(self) -> tuple[bool, list[str]]:
        """Fill all fields on the current Indeed page.

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
        """Fill standard text input fields."""
        inputs = self._page.locator(
            'input[type="text"], input[type="email"], input[type="tel"], input:not([type])'
        ).all()

        for inp in inputs:
            self._fill_input(inp, "text")

    def _fill_number_inputs(self) -> None:
        """Fill number input fields (experience questions)."""
        inputs = self._page.locator(
            'input[type="number"], input[id*="number-input"]'
        ).all()

        for inp in inputs:
            self._fill_input(inp, "number")

    def _fill_input(self, inp: Locator, field_type: str) -> None:
        """Fill a single input field."""
        try:
            if not inp.is_visible(timeout=500) or not inp.is_editable(timeout=500):
                return
        except Exception:
            return

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
                logger.warning(f"Fill failed for {question[:40]}: {e}")
        else:
            self._unknown_questions.append(question)
            logger.warning(f"Unknown question: {question[:60]}")

    def _fill_textareas(self) -> None:
        """Fill textarea fields (open-ended questions)."""
        textareas = self._page.locator(
            'textarea, [id*="rich-text-question-input"]'
        ).all()

        for ta in textareas:
            try:
                if not ta.is_visible(timeout=500):
                    continue
            except Exception:
                continue

            try:
                current = ta.input_value()
                if current and len(current.strip()) > 0:
                    continue
            except Exception:
                pass

            question = self._get_question_text(ta)
            if not question:
                continue

            answer = self._answers.get_answer(question, "text")

            if answer is not None:
                try:
                    ta.fill(str(answer))
                    logger.info(f"Filled textarea: {question[:40]}")
                except Exception as e:
                    logger.warning(f"Textarea fill failed: {e}")
            else:
                self._unknown_questions.append(question)

    def _fill_selects(self) -> None:
        """Fill select dropdowns."""
        selects = self._page.locator('select').all()

        for select in selects:
            try:
                if not select.is_visible(timeout=500):
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
                        logger.warning(f"Select failed for {question[:40]}: {e}")
            else:
                self._unknown_questions.append(question)

    def _fill_radios(self) -> None:
        """Fill radio button groups."""
        fieldsets = self._page.locator('fieldset, [role="radiogroup"]').all()

        for fieldset in fieldsets:
            try:
                if not fieldset.is_visible(timeout=500):
                    continue
            except Exception:
                continue

            question = self._get_fieldset_question(fieldset)
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
                if label and self._matches_answer(label, answer_str):
                    try:
                        if not radio.is_checked():
                            radio.check(force=True)
                            logger.info(f"Radio: {question[:40]} = {label}")
                    except Exception:
                        pass
                    break

    def _fill_checkboxes(self) -> None:
        """Fill checkboxes."""
        checkboxes = self._page.locator('input[type="checkbox"]').all()

        for cb in checkboxes:
            try:
                if not cb.is_visible(timeout=500):
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
                            cb.check(force=True)
                        else:
                            cb.uncheck(force=True)
                        logger.info(f"Checkbox: {question[:40]} = {should_check}")
                except Exception:
                    pass

    def _get_question_text(self, element: Locator) -> str:
        """Extract question text from element's context."""
        # Try aria-label first
        try:
            aria = element.get_attribute("aria-label")
            if aria and len(aria.strip()) > 2:
                return aria.strip()
        except Exception:
            pass

        # Try associated label via for attribute
        try:
            elem_id = element.get_attribute("id")
            if elem_id:
                label = self._page.locator(f'label[for="{elem_id}"]').first
                if label.count() > 0:
                    text = label.text_content()
                    if text and len(text.strip()) > 2:
                        return text.strip()
        except Exception:
            pass

        # Try parent label
        try:
            parent_label = element.locator('xpath=ancestor::label').first
            if parent_label.count() > 0:
                text = parent_label.text_content()
                if text and len(text.strip()) > 2:
                    return text.strip()
        except Exception:
            pass

        # Try placeholder
        try:
            placeholder = element.get_attribute("placeholder")
            if placeholder and len(placeholder.strip()) > 2:
                return placeholder.strip()
        except Exception:
            pass

        # Try preceding label or text
        try:
            container = element.locator('xpath=ancestor::div[contains(@class, "question")]').first
            if container.count() > 0:
                text = container.locator('label, .label, [class*="label"]').first.text_content()
                if text and len(text.strip()) > 2:
                    return text.strip()
        except Exception:
            pass

        # Try name attribute as last resort
        try:
            name = element.get_attribute("name")
            if name and len(name) > 2:
                return name.replace("_", " ").replace("-", " ")
        except Exception:
            pass

        return ""

    def _get_fieldset_question(self, fieldset: Locator) -> str:
        """Get question text for a fieldset/radiogroup."""
        try:
            legend = fieldset.locator('legend').first
            if legend.count() > 0:
                text = legend.text_content()
                if text:
                    return text.strip()
        except Exception:
            pass

        try:
            label = fieldset.locator('label').first
            if label.count() > 0:
                text = label.text_content()
                if text:
                    return text.strip()
        except Exception:
            pass

        try:
            aria = fieldset.get_attribute("aria-label")
            if aria:
                return aria.strip()
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
                return value
        except Exception:
            pass

        return ""

    def _matches_answer(self, label: str, answer: str) -> bool:
        """Check if label matches expected answer."""
        label_lower = label.lower().strip()
        answer_lower = answer.lower().strip()

        if answer_lower in label_lower:
            return True

        if answer_lower in ("yes", "true", "1"):
            return label_lower in ("yes", "true", "y")
        if answer_lower in ("no", "false", "0"):
            return label_lower in ("no", "false", "n")

        return False

    def click_continue(self) -> bool:
        """Click the Continue/Submit button."""
        patterns = self.SUBMIT_PATTERNS if self.is_review_page() else self.CONTINUE_PATTERNS

        for selector in patterns:
            try:
                btn = self._page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    self._page.wait_for_timeout(500)
                    logger.info(f"Clicked continue: {selector}")
                    return True
            except Exception:
                continue

        # Fallback: scroll and try again
        try:
            self._page.evaluate("window.scrollBy(0, 500)")
            self._page.wait_for_timeout(500)

            for selector in patterns[:4]:
                try:
                    btn = self._page.locator(selector).first
                    if btn.is_visible(timeout=1000):
                        btn.click()
                        logger.info(f"Clicked continue after scroll: {selector}")
                        return True
                except Exception:
                    continue
        except Exception:
            pass

        return False

    def is_success_page(self) -> bool:
        """Check if on success/confirmation page."""
        current_url = self._page.url.lower()

        if any(x in current_url for x in ["confirmation", "success", "thank"]):
            return True

        for indicator in self.SUCCESS_INDICATORS:
            try:
                if self._page.locator(indicator).first.is_visible(timeout=500):
                    return True
            except Exception:
                continue

        return False

    def is_review_page(self) -> bool:
        """Check if on review page (last step before submit)."""
        current_url = self._page.url.lower()
        return "review" in current_url

    def is_resume_page(self) -> bool:
        """Check if on resume selection page."""
        current_url = self._page.url.lower()
        return "resume" in current_url
