"""Deterministic form filler for LinkedIn Easy Apply."""
import logging

from playwright.sync_api import Page, Locator

from .answer_engine import AnswerEngine

logger = logging.getLogger(__name__)

# Fallback answers for unknown questions
FALLBACK_TEXT = "See resume"
FALLBACK_TEXTAREA = "Please refer to my resume and LinkedIn profile for detailed information on my experience and qualifications."


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
        """Fill all fields in the current Easy Apply modal.

        Returns:
            True if modal was found and processed, False if no modal.
        """
        # Try multiple modal selectors
        modal_selectors = [
            ".jobs-easy-apply-modal",
            "[data-test-modal]",
            ".artdeco-modal",
            '[role="dialog"]',
        ]

        modal = None
        for selector in modal_selectors:
            try:
                candidate = self._page.locator(selector).first
                if candidate.is_visible(timeout=1000):
                    modal = candidate
                    logger.info(f"Found modal with selector: {selector}")
                    break
            except Exception:
                continue

        if modal is None:
            logger.warning("No Easy Apply modal found with any selector")
            return False

        # Count fields before filling
        try:
            input_count = modal.locator("input:visible").count()
            select_count = modal.locator("select:visible").count()
            fieldset_count = modal.locator("fieldset:visible").count()
            logger.info(f"Modal has {input_count} inputs, {select_count} selects, {fieldset_count} fieldsets")
        except Exception as e:
            logger.debug(f"Could not count fields: {e}")

        self._fill_text_inputs(modal)
        self._fill_selects(modal)
        self._fill_radios(modal)
        self._fill_skill_checkboxes(modal)
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
            # Numeric fields need numbers, not "See resume"
            numeric_keywords = ["salary", "rate", "amount", "years", "months", "compensation", "pkr", "usd", "number"]
            if field_type == "number" or any(kw in question.lower() for kw in numeric_keywords):
                inp.fill("0")
                logger.info(f"Fallback numeric: {question[:50]} = 0")
            else:
                inp.fill(FALLBACK_TEXT)
                logger.info(f"Fallback text: {question[:50]}")
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
        """Fill a single select dropdown with intelligent option matching."""
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

        # Get all available options
        option_texts: list[tuple[str, str]] = []
        try:
            options = select.locator("option").all()
            for opt in options:
                text = (opt.text_content() or "").strip()
                val = opt.get_attribute("value") or ""
                if text and "select" not in text.lower():
                    option_texts.append((val, text))
        except Exception:
            pass

        if answer is not None:
            answer_str = str(answer).lower()

            # Try exact match first
            for val, text in option_texts:
                if answer_str == text.lower() or answer_str == val.lower():
                    try:
                        select.select_option(value=val, timeout=3000)
                        logger.info(f"Selected [{strategy}]: {question[:40]} = {text}")
                        return True
                    except Exception:
                        pass

            # Try partial/fuzzy match
            for val, text in option_texts:
                text_lower = text.lower()
                if answer_str in text_lower or text_lower.startswith(answer_str):
                    try:
                        select.select_option(value=val, timeout=3000)
                        logger.info(f"Selected [{strategy}]: {question[:40]} = {text}")
                        return True
                    except Exception:
                        pass

            # For numeric answers (years of experience), find best matching range
            if answer_str.isdigit():
                years = int(answer_str)
                best_match = self._find_best_years_option(years, option_texts)
                if best_match:
                    try:
                        select.select_option(value=best_match[0], timeout=3000)
                        logger.info(f"Selected [{strategy}]: {question[:40]} = {best_match[1]} (for {years} years)")
                        return True
                    except Exception:
                        pass

        # Fallback: select first non-placeholder option
        if option_texts:
            val, text = option_texts[0]
            try:
                select.select_option(value=val, timeout=3000)
                logger.info(f"Fallback select: {question[:50]} = {text}")
                return True
            except Exception as e:
                logger.warning(f"Fallback select failed: {e}")

        return True

    def _find_best_years_option(self, years: int, options: list[tuple[str, str]]) -> tuple[str, str] | None:
        """Find the best dropdown option for a given number of years experience."""
        import re

        # Exact match like "6 years" or "6"
        for val, text in options:
            text_lower = text.lower()
            if str(years) in text and ("year" in text_lower or text.strip().isdigit()):
                return (val, text)
            if f"{years}+" in text:
                return (val, text)

        # Range match (e.g., "5-7 years" for 6 years)
        for val, text in options:
            range_match = re.search(r"(\d+)\s*[-–]\s*(\d+)", text)
            if range_match:
                low, high = int(range_match.group(1)), int(range_match.group(2))
                if low <= years <= high:
                    return (val, text)

        # "X+" where X <= years (e.g., "5+" for 6 years)
        for val, text in options:
            plus_match = re.search(r"(\d+)\+", text)
            if plus_match:
                threshold = int(plus_match.group(1))
                if years >= threshold:
                    return (val, text)

        # Last resort: any option with a number <= years
        for val, text in options:
            num_match = re.search(r"(\d+)", text)
            if num_match and int(num_match.group(1)) <= years:
                return (val, text)

        return None

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
        """Fill a single radio group with intelligent defaults."""
        answer = self._answers.get_answer(question, "radio")

        try:
            radios = fieldset.locator(LinkedInSelectors.RADIO).all()
        except Exception:
            return False

        if not radios:
            return False

        # Build label map
        radio_labels: list[tuple[Locator, str]] = []
        for radio in radios:
            label = self._get_radio_label(radio)
            radio_labels.append((radio, label.lower() if label else ""))

        # If we have an explicit answer, use it
        if answer is not None:
            answer_str = str(answer).lower()
            for radio, label in radio_labels:
                if label and answer_str in label:
                    try:
                        if not radio.is_checked():
                            self._click_radio_label(radio)
                            logger.info(f"Radio [{strategy}]: {question[:40]} = {label}")
                    except Exception:
                        pass
                    return True

        # NO ANSWER - determine safe default based on question content
        q_lower = question.lower()

        # Questions that should default to "No"
        should_default_no = any(phrase in q_lower for phrase in [
            "previously employed", "former employee", "worked here before",
            "been employed by", "worked at", "worked for",
            "referred by", "referred to", "referral", "who referred",
            "close relative", "conflict of interest", "financial interest",
            "ethereum", "ens", "basename", "wallet", "crypto", "smart contract",
            "government official", "political", "public official",
            "finra", "sec registration", "securities license", "broker",
            "convicted", "felony", "criminal",
            "non-compete", "non-disclosure",
            "lawsuit", "litigation", "legal action",
        ])

        # Questions that should default to "Yes"
        should_default_yes = any(phrase in q_lower for phrase in [
            "legally authorized", "authorized to work", "eligible to work",
            "background check", "drug test", "drug screen",
            "18 years", "over 18", "of age",
            "agree", "consent", "acknowledge", "certify", "confirm",
            "comfortable", "willing",
            "start immediately", "available to start",
        ])

        # Find Yes and No options
        yes_radio = None
        no_radio = None
        for radio, label in radio_labels:
            if label in ("yes", "true"):
                yes_radio = radio
            elif label in ("no", "false"):
                no_radio = radio

        # Apply default based on question type
        if should_default_no and no_radio:
            try:
                if not no_radio.is_checked():
                    self._click_radio_label(no_radio)
                    logger.info(f"Radio default NO [{strategy}]: {question[:40]}")
            except Exception:
                pass
            return True

        if should_default_yes and yes_radio:
            try:
                if not yes_radio.is_checked():
                    self._click_radio_label(yes_radio)
                    logger.info(f"Radio default YES [{strategy}]: {question[:40]}")
            except Exception:
                pass
            return True

        # Unknown question - default to "No" as safer option
        if no_radio:
            try:
                if not no_radio.is_checked():
                    self._click_radio_label(no_radio)
                    logger.info(f"Radio fallback NO (safe) [{strategy}]: {question[:40]}")
            except Exception:
                pass
            return True

        # Last resort - use first option (non-Yes/No radio groups)
        if radios:
            first_radio = radios[0]
            first_label = self._get_radio_label(first_radio)
            try:
                if not first_radio.is_checked():
                    self._click_radio_label(first_radio)
                    logger.info(f"Radio fallback (first) [{strategy}]: {question[:40]} = {first_label}")
            except Exception:
                pass

        return True

    def _click_radio_label(self, radio: Locator) -> None:
        """Click the label for a radio button instead of the input directly.
        
        LinkedIn's labels intercept pointer events, so we must click the label.
        """
        try:
            radio_id = radio.get_attribute("id")
            if radio_id:
                label = self._page.locator(f'label[for="{radio_id}"]').first
                if label.is_visible(timeout=1000):
                    label.click(timeout=3000)
                    return
        except Exception:
            pass
        # Fallback: try force click on the radio itself
        try:
            radio.click(force=True, timeout=3000)
        except Exception:
            pass

    def _fill_checkboxes(self, container: Locator) -> None:
        """Fill checkboxes - only check boxes we have explicit answers for."""
        try:
            checkboxes = container.locator('input[type="checkbox"]').all()
        except Exception:
            return

        for cb in checkboxes:
            try:
                if not cb.is_visible(timeout=1000):
                    continue
            except Exception:
                continue

            question = self._get_question_text(cb)
            if not question:
                continue

            # Skip spam checkboxes
            q_lower = question.lower()
            spam_keywords = ["follow", "marketing", "newsletter", "subscribe", "updates"]
            if any(kw in q_lower for kw in spam_keywords):
                logger.debug(f"Skipping spam checkbox: {question[:50]}")
                continue

            answer = self._answers.get_answer(question, "checkbox")
            if answer is None:
                # DO NOT auto-check unknown checkboxes!
                logger.debug(f"No answer for checkbox, skipping: {question[:50]}")
                continue

            should_check = bool(answer)
            try:
                if cb.is_checked() != should_check:
                    self._click_checkbox_label(cb)
                    logger.info(f"Checkbox: {question[:40]} = {should_check}")
            except Exception:
                pass

    def _click_checkbox_label(self, checkbox: Locator) -> None:
        """Click the label for a checkbox instead of the input directly."""
        try:
            cb_id = checkbox.get_attribute("id")
            if cb_id:
                label = self._page.locator(f'label[for="{cb_id}"]').first
                if label.is_visible(timeout=1000):
                    label.click(timeout=2000)
                    return
        except Exception:
            pass
        # Fallback: force click
        try:
            checkbox.click(force=True, timeout=2000)
        except Exception:
            pass

    def _fill_skill_checkboxes(self, container: Locator) -> None:
        """Fill multi-select skill checkboxes intelligently based on user's actual skills."""
        try:
            fieldsets = container.locator("fieldset").all()
        except Exception:
            return

        # Load user's skills from config
        skills_config = self._answers._config.get("skills", {})
        all_skills: set[str] = set()
        for category_skills in skills_config.values():
            if isinstance(category_skills, list):
                all_skills.update(s.lower() for s in category_skills)

        for fieldset in fieldsets:
            try:
                question = self._get_fieldset_question(fieldset)
                if not question:
                    continue

                q_lower = question.lower()
                # Only process multi-select skill questions
                if "select all" not in q_lower and "check all" not in q_lower:
                    continue
                skill_indicators = ["coding", "language", "experience", "following", "skill", "technolog"]
                if not any(ind in q_lower for ind in skill_indicators):
                    continue

                checkboxes = fieldset.locator('input[type="checkbox"]').all()
                if len(checkboxes) < 2:
                    continue

                checked_any = False
                for cb in checkboxes:
                    try:
                        if cb.is_checked():
                            continue

                        label = self._get_checkbox_label(cb)
                        if not label:
                            continue

                        label_lower = label.lower().strip()

                        # NEVER check "None of the above"
                        if "none" in label_lower and "above" in label_lower:
                            continue

                        # Check if this skill/option matches user's skills
                        should_check = self._skill_matches(label_lower, all_skills)

                        if should_check:
                            self._click_checkbox_label(cb)
                            checked_any = True
                            logger.info(f"Skill checkbox: {question[:30]} -> checked '{label}'")

                    except Exception as e:
                        logger.debug(f"Checkbox processing error: {e}")
                        continue

                if not checked_any:
                    # If no skills matched, check first non-"none" option as fallback
                    for cb in checkboxes:
                        label = self._get_checkbox_label(cb)
                        if label and "none" not in label.lower():
                            self._click_checkbox_label(cb)
                            logger.info(f"Fallback skill checkbox: {question[:30]} -> '{label}'")
                            break

            except Exception as e:
                logger.debug(f"Skill fieldset processing failed: {e}")

    def _skill_matches(self, label: str, skills: set[str]) -> bool:
        """Check if a checkbox label matches any of the user's skills."""
        # Direct skill match
        if label in skills:
            return True
        # Partial match (e.g., "Python" matches "python")
        if any(skill in label or label in skill for skill in skills):
            return True
        # Common mappings
        if "backend" in label or "back-end" in label or "back end" in label:
            return "backend" in skills or "api" in skills
        if "cloud" in label or "aws" in label or "gcp" in label or "azure" in label:
            return "aws" in skills or "cloud infrastructure" in skills
        if "ci/cd" in label or "deployment" in label or "pipeline" in label:
            return "ci/cd" in skills or "ci/cd pipelines" in skills
        if "platform" in label or "infrastructure" in label:
            return "platform services" in skills or "aws" in skills
        if "tooling" in label or "developer tool" in label:
            return "internal developer tooling" in skills
        if "core backend" in label:
            return "core backend" in skills or "backend" in skills
        return False

    def _get_fieldset_question(self, fieldset: Locator) -> str:
        """Extract question text from fieldset legend or label."""
        for selector in ["legend", "span.fb-form-element-label", ".visually-hidden"]:
            try:
                el = fieldset.locator(selector).first
                if el.count() > 0:
                    text = el.text_content()
                    if text:
                        return text.strip()
            except Exception:
                pass
        return ""

    def _get_checkbox_label(self, checkbox: Locator) -> str:
        """Get label text for a checkbox."""
        try:
            cb_id = checkbox.get_attribute("id")
            if cb_id:
                label = self._page.locator(f'label[for="{cb_id}"]').first
                if label.count() > 0:
                    return (label.text_content() or "").strip()
        except Exception:
            pass
        try:
            parent = checkbox.locator("xpath=ancestor::label").first
            if parent.count() > 0:
                return (parent.text_content() or "").strip()
        except Exception:
            pass
        return ""

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
                textarea.fill(FALLBACK_TEXTAREA)
                logger.info(f"Using fallback for unknown question: {question[:50]}")

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
                    btn_text = btn.text_content() or btn.get_attribute("aria-label") or selector
                    btn.click()
                    logger.info(f"Clicked button: {btn_text[:30]}")
                    self._page.wait_for_timeout(500)
                    return True
            except Exception as e:
                logger.debug(f"Button selector {selector} failed: {e}")
                continue

        logger.warning("No next/submit button found with any selector")
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
