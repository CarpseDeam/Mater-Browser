"""Deterministic form filler for LinkedIn Easy Apply."""
import logging

from playwright.sync_api import Page, Locator

from .answer_engine import AnswerEngine

logger = logging.getLogger(__name__)


class LinkedInSelectors:
    """Industry-standard selectors from established LinkedIn Easy Apply bots."""

    # Form structure
    FORM_SECTION = ".jobs-easy-apply-form-section__grouping"
    FORM_ELEMENT = ".jobs-easy-apply-form-element"

    # Text inputs
    TEXT_INPUT = ".artdeco-text-input--input"
    TEXT_INPUT_ALT = ".fb-single-line-text__input"

    # Radio buttons
    RADIO = "input[type='radio']"
    RADIO_FIELDSET = "fieldset[data-test-form-builder-radio-button-form-component='true']"
    RADIO_TITLE = "span[data-test-form-builder-radio-button-form-component__title]"

    # Dropdowns/Selects
    DROPDOWN = ".fb-dropdown__select"
    SELECT = "select"

    # Multi-select / typeahead
    MULTI_SELECT = "[id*='text-entity-list-form-component']"
    TEXT_ENTITY_LIST = "div[data-test-text-entity-list-form-component]"
    SINGLE_LINE_TEXT = "div[data-test-single-line-text-form-component]"

    # Textarea
    TEXTAREA = "textarea"

    # Labels
    QUESTION_LABEL = ".fb-form-element-label"
    VISUALLY_HIDDEN = ".visually-hidden"

    # Buttons
    EASY_APPLY_BUTTON = "button.jobs-apply-button"
    REVIEW_BUTTON = "button[aria-label='Review your application']"
    SUBMIT_BUTTON = "button[aria-label='Submit application']"
    PRIMARY_BUTTON = ".artdeco-button--primary"
    NEXT_BUTTON = "button[aria-label='Continue to next step']"

    # File upload
    RESUME_INPUT = "[id*='jobs-document-upload-file-input-upload-resume']"
    COVER_LETTER_INPUT = "[id*='jobs-document-upload-file-input-upload-cover-letter']"
    FILE_INPUT = "input[name='file']"
    CHOOSE_RESUME = "[aria-label='Choose Resume']"

    # Follow checkbox
    FOLLOW_CHECKBOX = "label[for='follow-company-checkbox']"
    FOLLOW_LABEL = "text='to stay up to date with their page'"

    # Errors
    ERROR_MESSAGE = ".artdeco-inline-feedback__message"

    # Confirmation/Success
    APPLICATION_SENT = "text='Application sent'"
    APPLICATION_SENT_ALT = "text='Your application was sent'"
    POST_APPLY_MODAL = "[data-test-modal-id='post-apply-modal']"
    MODAL_HEADER_SENT = ".artdeco-modal__header:has-text('Application sent')"


class LinkedInFormFiller:
    """Fill LinkedIn Easy Apply forms using config-driven answers."""

    SUBMIT_BUTTON_PATTERNS = [
        # Final submit (most specific first)
        'button[aria-label="Submit application"]',
        # Next/Continue/Review
        'button[aria-label*="Submit" i]',
        'button[aria-label*="Review" i]',
        'button[aria-label*="Next" i]',
        '.artdeco-button--primary',
        'button:has-text("Submit application")',
        'button:has-text("Review")',
        'button:has-text("Next")',
        'button:has-text("Continue")',
        'button[type="submit"]',
    ]

    def __init__(self, page: Page, answer_engine: AnswerEngine | None = None) -> None:
        self._page = page
        self._answers = answer_engine or AnswerEngine()

    def fill_current_modal(self) -> bool:
        """Fill all fields in the current Easy Apply modal. Fire and forget.

        Returns:
            True if modal was found and processed, False if no modal.
        """
        modal = self._page.locator('.jobs-easy-apply-modal, [data-test-modal]').first
        try:
            if not modal.is_visible(timeout=2000):
                logger.warning("No Easy Apply modal found")
                return False
        except Exception:
            logger.warning("No Easy Apply modal found")
            return False

        self._fill_text_inputs(modal)
        self._fill_selects(modal)
        self._fill_radios(modal)
        self._fill_checkboxes(modal)
        self._fill_textareas(modal)
        self._uncheck_follow_company()

        return True

    def _fill_text_inputs(self, container: Locator) -> None:
        """Fill text input fields using multiple selector strategies."""
        S = LinkedInSelectors
        selector_strategies = [
            (S.TEXT_INPUT, "artdeco-text-input"),
            (S.TEXT_INPUT_ALT, "fb-single-line-text"),
            ('input[type="text"]', "input[type=text]"),
            ('input[type="email"]', "email"),
            ('input[type="tel"]', "tel"),
            ('input[type="number"]', "number"),
            ('input:not([type])', "input-no-type"),
        ]

        filled_ids = set()
        for selector, strategy_name in selector_strategies:
            try:
                inputs = container.locator(selector).all()
            except Exception:
                continue

            for inp in inputs:
                inp_id = self._get_element_id(inp)
                if inp_id in filled_ids:
                    continue

                if not self._fill_single_text_input(inp, strategy_name):
                    continue
                if inp_id:
                    filled_ids.add(inp_id)

    def _fill_single_text_input(self, inp: Locator, strategy: str) -> bool:
        """Fill a single text input. Returns True if field was processed."""
        try:
            if not inp.is_visible() or not inp.is_editable():
                return False
        except Exception:
            return False

        try:
            current_value = inp.input_value()
            if current_value and len(current_value.strip()) > 0:
                return False
        except Exception:
            pass

        question = self._get_question_text(inp)
        if not question:
            return False

        field_type = inp.get_attribute("type") or "text"
        answer = self._answers.get_answer(question, field_type)

        if answer is not None:
            if self._is_location_field(question):
                self._fill_autocomplete_location(inp, str(answer), question)
            else:
                inp.fill(str(answer))
                logger.info(f"Filled [{strategy}]: {question[:40]} = {answer}")
        else:
            logger.info(f"Skipped (no answer): {question[:50]}")
        return True

    def _get_element_id(self, element: Locator) -> str:
        """Get element ID or generate one from attributes."""
        try:
            return element.get_attribute("id") or element.get_attribute("name") or ""
        except Exception:
            return ""

    def _fill_selects(self, container: Locator) -> None:
        """Fill select dropdowns using multiple selector strategies."""
        S = LinkedInSelectors
        selector_strategies = [
            (S.SELECT, "select"),
            (S.DROPDOWN, "fb-dropdown"),
        ]

        filled_ids = set()
        for selector, strategy_name in selector_strategies:
            try:
                selects = container.locator(selector).all()
            except Exception:
                continue

            for select in selects:
                select_id = self._get_element_id(select)
                if select_id in filled_ids:
                    continue

                if self._fill_single_select(select, strategy_name):
                    if select_id:
                        filled_ids.add(select_id)

    def _fill_single_select(self, select: Locator, strategy: str) -> bool:
        """Fill a single select dropdown. Returns True if processed."""
        try:
            if not select.is_visible():
                return False
        except Exception:
            return False

        try:
            current_value = select.input_value()
            if current_value and current_value.strip():
                logger.debug(f"Skipping pre-filled select [{strategy}]")
                return False
        except Exception:
            pass

        question = self._get_question_text(select)
        if not question:
            return False

        answer = self._answers.get_answer(question, "select")
        if answer is not None:
            try:
                select.select_option(label=str(answer), timeout=5000)
                logger.info(f"Selected [{strategy}]: {question[:40]} = {answer}")
                return True
            except Exception:
                try:
                    select.select_option(value=str(answer), timeout=5000)
                    logger.info(f"Selected [{strategy}]: {question[:40]} = {answer}")
                    return True
                except Exception as e:
                    logger.warning(f"Could not select {answer} for {question}: {e}")
                    return False
        else:
            logger.info(f"Skipped select (no answer): {question[:50]}")
            return True

    def _fill_radios(self, container: Locator) -> None:
        """Fill radio button groups using multiple selector strategies."""
        S = LinkedInSelectors
        fieldset_selectors = [
            (S.RADIO_FIELDSET, "data-test-radio"),
            ("fieldset", "fieldset"),
        ]

        filled_questions = set()
        for selector, strategy_name in fieldset_selectors:
            try:
                fieldsets = container.locator(selector).all()
            except Exception:
                continue

            for fieldset in fieldsets:
                question = self._get_radio_group_question(fieldset)
                if not question or question in filled_questions:
                    continue

                if self._fill_single_radio_group(fieldset, question, strategy_name):
                    filled_questions.add(question)

    def _get_radio_group_question(self, fieldset: Locator) -> str:
        """Extract question text from radio group fieldset."""
        S = LinkedInSelectors
        try:
            if not fieldset.is_visible():
                return ""
        except Exception:
            return ""

        # Try data-test title span first
        try:
            title = fieldset.locator(S.RADIO_TITLE).first
            if title.count() > 0:
                text = title.text_content()
                if text:
                    return text.strip()
        except Exception:
            pass

        # Try legend
        try:
            legend = fieldset.locator("legend").first
            if legend.count() > 0:
                text = legend.text_content()
                if text:
                    return text.strip()
        except Exception:
            pass

        # Try visually-hidden span
        try:
            hidden = fieldset.locator(S.VISUALLY_HIDDEN).first
            if hidden.count() > 0:
                text = hidden.text_content()
                if text:
                    return text.strip()
        except Exception:
            pass

        return ""

    def _fill_single_radio_group(self, fieldset: Locator, question: str, strategy: str) -> bool:
        """Fill a single radio group. Returns True if processed."""
        answer = self._answers.get_answer(question, "radio")
        if answer is None:
            logger.info(f"Skipped radio (no answer): {question[:50]}")
            return True

        answer_str = str(answer).lower()
        try:
            radios = fieldset.locator(LinkedInSelectors.RADIO).all()
        except Exception:
            return False

        for radio in radios:
            label = self._get_radio_label(radio)
            if label and answer_str in label.lower():
                try:
                    if not radio.is_checked():
                        radio.check()
                        logger.info(f"Radio [{strategy}]: {question[:40]} = {label}")
                except Exception:
                    pass
                return True
        return False

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

    def _fill_textareas(self, container: Locator) -> None:
        """Fill textarea fields within form sections."""
        S = LinkedInSelectors
        try:
            textareas = container.locator(S.TEXTAREA).all()
        except Exception:
            return

        for textarea in textareas:
            try:
                if not textarea.is_visible() or not textarea.is_editable():
                    continue
            except Exception:
                continue

            try:
                current_value = textarea.input_value()
                if current_value and len(current_value.strip()) > 0:
                    continue
            except Exception:
                pass

            question = self._get_question_text(textarea)
            if not question:
                continue

            answer = self._answers.get_answer(question, "textarea")
            if answer is not None:
                textarea.fill(str(answer))
                logger.info(f"Textarea: {question[:40]} = {str(answer)[:30]}...")
            else:
                fallback = "Please see my resume for details."
                textarea.fill(fallback)
                logger.info(f"Textarea (fallback): {question[:40]} = {fallback}")

    def _uncheck_follow_company(self) -> None:
        """Uncheck the follow company checkbox if present."""
        S = LinkedInSelectors
        selectors = [S.FOLLOW_CHECKBOX, S.FOLLOW_LABEL]

        for selector in selectors:
            try:
                el = self._page.locator(selector).first
                if not el.is_visible(timeout=500):
                    continue

                checkbox = self._page.locator("#follow-company-checkbox").first
                if checkbox.count() > 0 and checkbox.is_checked():
                    el.click()
                    logger.info("Unchecked follow company checkbox")
                    return
            except Exception:
                continue

    def _get_question_text(self, element: Locator) -> str:
        """Extract question text from element's label, aria-label, or placeholder."""
        S = LinkedInSelectors

        # Try aria-label first
        try:
            aria = element.get_attribute("aria-label")
            if aria:
                return aria.strip()
        except Exception:
            pass

        # Try label[for=id]
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

        # Try .fb-form-element-label within parent form element
        try:
            parent_form = element.locator(f"xpath=ancestor::{S.FORM_ELEMENT[1:]}").first
            if parent_form.count() > 0:
                label = parent_form.locator(S.QUESTION_LABEL).first
                if label.count() > 0:
                    text = label.text_content()
                    if text:
                        return text.strip()
        except Exception:
            pass

        # Try ancestor label
        try:
            parent_label = element.locator("xpath=ancestor::label").first
            if parent_label.count() > 0:
                text = parent_label.text_content()
                if text:
                    return text.strip()
        except Exception:
            pass

        # Try placeholder
        try:
            placeholder = element.get_attribute("placeholder")
            if placeholder:
                return placeholder.strip()
        except Exception:
            pass

        # Try preceding sibling label
        try:
            prev_label = element.locator("xpath=preceding-sibling::label[1]").first
            if prev_label.count() > 0:
                text = prev_label.text_content()
                if text:
                    return text.strip()
        except Exception:
            pass

        return ""

    def _is_location_field(self, question: str) -> bool:
        """Check if this is a location/city autocomplete field."""
        q_lower = question.lower()
        return any(kw in q_lower for kw in ["location", "city", "where are you located"])

    def _fill_autocomplete_location(self, inp: Locator, answer: str, question: str) -> None:
        """Fill LinkedIn autocomplete location field.
        
        LinkedIn location fields require typing to trigger suggestions,
        then selecting from the dropdown.
        """
        try:
            inp.click()
            self._page.wait_for_timeout(200)
            
            inp.fill("")
            self._page.wait_for_timeout(100)
            
            inp.type(answer, delay=50)
            self._page.wait_for_timeout(800)
            
            suggestion_selectors = [
                '.basic-typeahead__selectable:first-child',
                '[role="option"]:first-child',
                '.search-typeahead-v2__hit:first-child',
                '.typeahead-results__item:first-child',
            ]
            
            for selector in suggestion_selectors:
                try:
                    suggestion = self._page.locator(selector).first
                    if suggestion.is_visible(timeout=500):
                        suggestion.click()
                        logger.info(f"Autocomplete: {question[:40]} = {answer} (selected suggestion)")
                        return
                except Exception:
                    continue
            
            self._page.keyboard.press("Enter")
            logger.info(f"Autocomplete: {question[:40]} = {answer} (pressed Enter)")
            
        except Exception as e:
            logger.warning(f"Autocomplete fill failed for {question}: {e}")
            try:
                inp.fill(answer)
                logger.info(f"Fallback fill: {question[:40]} = {answer}")
            except Exception:
                pass

    def _get_radio_label(self, radio: Locator) -> str:
        """Get label text for a radio button."""
        S = LinkedInSelectors

        # Try label[for=id] first
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

        # Try visually-hidden span within parent label
        try:
            parent = radio.locator("xpath=ancestor::label").first
            if parent.count() > 0:
                hidden = parent.locator(S.VISUALLY_HIDDEN).first
                if hidden.count() > 0:
                    text = hidden.text_content()
                    if text:
                        return text.strip()
                # Fallback to full label text
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
        S = LinkedInSelectors
        indicators = [
            S.APPLICATION_SENT,
            S.APPLICATION_SENT_ALT,
            S.POST_APPLY_MODAL,
            S.MODAL_HEADER_SENT,
            'h2:has-text("Application sent")',
        ]
        for indicator in indicators:
            try:
                if self._page.locator(indicator).first.is_visible(timeout=500):
                    logger.debug(f"Confirmation detected via: {indicator}")
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
