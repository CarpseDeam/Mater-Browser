"""Tests for IndeedFormFiller."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from playwright.sync_api import Page, Locator

from src.agent.indeed_form_filler import IndeedFormFiller
from src.agent.answer_engine import AnswerEngine


@pytest.fixture
def mock_page() -> Mock:
    """Create a mock Playwright page."""
    page = Mock(spec=Page)
    page.locator = Mock(return_value=Mock(spec=Locator))
    page.wait_for_timeout = Mock()
    return page


@pytest.fixture
def mock_answer_engine() -> Mock:
    """Create a mock AnswerEngine."""
    engine = Mock(spec=AnswerEngine)
    engine.get_answer = Mock(return_value=None)
    return engine


@pytest.fixture
def filler(mock_page: Mock, mock_answer_engine: Mock) -> IndeedFormFiller:
    """Create an IndeedFormFiller instance."""
    return IndeedFormFiller(mock_page, mock_answer_engine)


def create_mock_locator(
    visible: bool = True,
    editable: bool = True,
    disabled: bool = False,
    value: str = "",
    text_content: str = "",
    aria_label: str | None = None,
    elem_id: str | None = None,
    placeholder: str | None = None,
    checked: bool = False,
    attr_type: str | None = None,
    name: str | None = None,
) -> Mock:
    """Create a mock Locator with configurable properties."""
    locator = Mock(spec=Locator)
    locator.is_visible = Mock(return_value=visible)
    locator.is_editable = Mock(return_value=editable)
    locator.is_disabled = Mock(return_value=disabled)
    locator.is_enabled = Mock(return_value=not disabled)
    locator.input_value = Mock(return_value=value)
    locator.text_content = Mock(return_value=text_content)
    locator.is_checked = Mock(return_value=checked)
    locator.fill = Mock()
    locator.check = Mock()
    locator.uncheck = Mock()
    locator.click = Mock()
    locator.select_option = Mock()
    locator.count = Mock(return_value=1 if visible else 0)
    locator.all = Mock(return_value=[locator])
    locator.first = locator

    def get_attr(attr: str) -> str | None:
        attrs = {
            "aria-label": aria_label,
            "id": elem_id,
            "placeholder": placeholder,
            "type": attr_type,
            "name": name,
            "value": value,
        }
        return attrs.get(attr)

    locator.get_attribute = Mock(side_effect=get_attr)
    locator.locator = Mock(return_value=locator)
    return locator


class TestInit:
    """Tests for IndeedFormFiller initialization."""

    def test_init_with_answer_engine(self, mock_page: Mock, mock_answer_engine: Mock) -> None:
        """Initialize with provided AnswerEngine."""
        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        assert filler._page is mock_page
        assert filler._answers is mock_answer_engine

    def test_init_without_answer_engine(self, mock_page: Mock) -> None:
        """Initialize with default AnswerEngine."""
        with patch.object(AnswerEngine, "__init__", return_value=None):
            filler = IndeedFormFiller(mock_page, None)
            assert filler._page is mock_page
            assert isinstance(filler._answers, AnswerEngine)


class TestFillTextInputs:
    """Tests for text input filling."""

    def test_fill_text_input_with_known_answer(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Fill text input when AnswerEngine has answer."""
        mock_input = create_mock_locator(aria_label="First Name")
        mock_page.locator.return_value.all.return_value = [mock_input]
        mock_answer_engine.get_answer.return_value = "John"

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        success, unknown = filler.fill_current_page()

        mock_input.fill.assert_called_with("John")
        assert success is True
        assert unknown == []

    def test_fill_email_input(self, mock_page: Mock, mock_answer_engine: Mock) -> None:
        """Fill email input field."""
        mock_input = create_mock_locator(aria_label="Email Address", attr_type="email")
        mock_page.locator.return_value.all.return_value = [mock_input]
        mock_answer_engine.get_answer.return_value = "test@example.com"

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_text_inputs()

        mock_input.fill.assert_called_with("test@example.com")

    def test_fill_phone_input(self, mock_page: Mock, mock_answer_engine: Mock) -> None:
        """Fill phone input field."""
        mock_input = create_mock_locator(aria_label="Phone Number", attr_type="tel")
        mock_page.locator.return_value.all.return_value = [mock_input]
        mock_answer_engine.get_answer.return_value = "555-1234"

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_text_inputs()

        mock_input.fill.assert_called_with("555-1234")

    def test_unknown_question_added_to_list(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Add unknown question to list when no match."""
        mock_input = create_mock_locator(aria_label="Custom Question")
        mock_page.locator.return_value.all.return_value = [mock_input]
        mock_answer_engine.get_answer.return_value = None

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        success, unknown = filler.fill_current_page()

        assert success is False
        assert "Custom Question" in unknown


class TestFillNumberInputs:
    """Tests for number input filling."""

    def test_fill_years_of_experience(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Fill years of experience number input."""
        mock_input = create_mock_locator(
            aria_label="Years of Python experience", attr_type="number"
        )

        def locator_side_effect(selector: str) -> Mock:
            mock = Mock(spec=Locator)
            if "number" in selector:
                mock.all.return_value = [mock_input]
            else:
                mock.all.return_value = []
            mock.first = mock
            mock.count.return_value = 0
            mock.is_visible.return_value = False
            return mock

        mock_page.locator.side_effect = locator_side_effect
        mock_answer_engine.get_answer.return_value = 5

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_number_inputs()

        mock_input.fill.assert_called_with("5")


class TestFillTextareas:
    """Tests for textarea filling."""

    def test_fill_open_ended_question(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Fill open-ended textarea question."""
        mock_textarea = create_mock_locator(aria_label="Why do you want this job?")

        def locator_side_effect(selector: str) -> Mock:
            mock = Mock(spec=Locator)
            if "textarea" in selector:
                mock.all.return_value = [mock_textarea]
            else:
                mock.all.return_value = []
            mock.first = mock
            mock.count.return_value = 0
            mock.is_visible.return_value = False
            return mock

        mock_page.locator.side_effect = locator_side_effect
        mock_answer_engine.get_answer.return_value = "I am passionate about..."

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_textareas()

        mock_textarea.fill.assert_called_with("I am passionate about...")

    def test_skip_textarea_no_match(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Skip textarea when no answer match and add to unknown."""
        mock_textarea = create_mock_locator(aria_label="Describe your experience")

        def locator_side_effect(selector: str) -> Mock:
            mock = Mock(spec=Locator)
            if "textarea" in selector:
                mock.all.return_value = [mock_textarea]
            else:
                mock.all.return_value = []
            mock.first = mock
            mock.count.return_value = 0
            mock.is_visible.return_value = False
            return mock

        mock_page.locator.side_effect = locator_side_effect
        mock_answer_engine.get_answer.return_value = None

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_textareas()

        mock_textarea.fill.assert_not_called()
        assert "Describe your experience" in filler._unknown_questions


class TestFillRadioButtons:
    """Tests for radio button filling."""

    def test_fill_yes_no_radio(self, mock_page: Mock, mock_answer_engine: Mock) -> None:
        """Fill Yes/No radio button question."""
        mock_yes_radio = create_mock_locator(elem_id="yes-radio")
        mock_no_radio = create_mock_locator(elem_id="no-radio")

        mock_legend = Mock(spec=Locator)
        mock_legend.count.return_value = 1
        mock_legend.text_content.return_value = "Are you authorized to work?"
        mock_legend.first = mock_legend

        mock_yes_label = Mock(spec=Locator)
        mock_yes_label.count.return_value = 1
        mock_yes_label.text_content.return_value = "Yes"
        mock_yes_label.first = mock_yes_label

        mock_no_label = Mock(spec=Locator)
        mock_no_label.count.return_value = 1
        mock_no_label.text_content.return_value = "No"
        mock_no_label.first = mock_no_label

        mock_radios_locator = Mock(spec=Locator)
        mock_radios_locator.all.return_value = [mock_yes_radio, mock_no_radio]

        mock_fieldset = Mock(spec=Locator)
        mock_fieldset.is_visible.return_value = True
        mock_fieldset.get_attribute.return_value = None

        def fieldset_locator(selector: str) -> Mock:
            if "legend" in selector:
                return mock_legend
            if 'input[type="radio"]' in selector:
                return mock_radios_locator
            empty = Mock(spec=Locator)
            empty.count.return_value = 0
            empty.first = empty
            return empty

        mock_fieldset.locator = Mock(side_effect=fieldset_locator)

        mock_fieldsets_locator = Mock(spec=Locator)
        mock_fieldsets_locator.all.return_value = [mock_fieldset]

        def page_locator(selector: str) -> Mock:
            if "fieldset" in selector or "radiogroup" in selector:
                return mock_fieldsets_locator
            if 'label[for="yes-radio"]' in selector:
                return mock_yes_label
            if 'label[for="no-radio"]' in selector:
                return mock_no_label
            mock = Mock(spec=Locator)
            mock.all.return_value = []
            mock.first = mock
            mock.count.return_value = 0
            mock.is_visible.return_value = False
            return mock

        mock_page.locator = Mock(side_effect=page_locator)
        mock_answer_engine.get_answer.return_value = "Yes"

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_radios()

        mock_yes_radio.check.assert_called_once()


class TestFillCheckboxes:
    """Tests for checkbox filling."""

    def test_check_checkbox_true(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Check checkbox when answer is True."""
        mock_checkbox = create_mock_locator(aria_label="I agree to terms", checked=False)

        def locator_side_effect(selector: str) -> Mock:
            mock = Mock(spec=Locator)
            if "checkbox" in selector:
                mock.all.return_value = [mock_checkbox]
            else:
                mock.all.return_value = []
            mock.first = mock
            mock.count.return_value = 0
            mock.is_visible.return_value = False
            return mock

        mock_page.locator.side_effect = locator_side_effect
        mock_answer_engine.get_answer.return_value = True

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_checkboxes()

        mock_checkbox.check.assert_called_once()

    def test_uncheck_checkbox_false(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Uncheck checkbox when answer is False."""
        mock_checkbox = create_mock_locator(
            aria_label="Subscribe to newsletter", checked=True
        )

        def locator_side_effect(selector: str) -> Mock:
            mock = Mock(spec=Locator)
            if "checkbox" in selector:
                mock.all.return_value = [mock_checkbox]
            else:
                mock.all.return_value = []
            mock.first = mock
            mock.count.return_value = 0
            mock.is_visible.return_value = False
            return mock

        mock_page.locator.side_effect = locator_side_effect
        mock_answer_engine.get_answer.return_value = False

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_checkboxes()

        mock_checkbox.uncheck.assert_called_once()


class TestFillSelectDropdowns:
    """Tests for select dropdown filling."""

    def test_fill_select_by_label(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Fill select dropdown by option label."""
        mock_select = create_mock_locator(aria_label="Country")

        def locator_side_effect(selector: str) -> Mock:
            mock = Mock(spec=Locator)
            if selector == "select":
                mock.all.return_value = [mock_select]
            else:
                mock.all.return_value = []
            mock.first = mock
            mock.count.return_value = 0
            mock.is_visible.return_value = False
            return mock

        mock_page.locator.side_effect = locator_side_effect
        mock_answer_engine.get_answer.return_value = "United States"

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_selects()

        mock_select.select_option.assert_called_with(label="United States")


class TestQuestionExtraction:
    """Tests for question text extraction."""

    def test_extract_from_aria_label(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Extract question from aria-label attribute."""
        mock_input = create_mock_locator(aria_label="Your Email Address")
        mock_page.locator.return_value.all.return_value = [mock_input]
        mock_answer_engine.get_answer.return_value = "test@test.com"

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_text_inputs()

        mock_answer_engine.get_answer.assert_called_with("Your Email Address", "text")

    def test_extract_from_label_for(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Extract question from label[for] element."""
        mock_input = create_mock_locator(elem_id="email-field")

        mock_label = Mock(spec=Locator)
        mock_label.count.return_value = 1
        mock_label.text_content.return_value = "Email Address"
        mock_label.first = mock_label

        mock_inputs_locator = Mock(spec=Locator)
        mock_inputs_locator.all.return_value = [mock_input]

        def page_locator(selector: str) -> Mock:
            if 'label[for="email-field"]' in selector:
                return mock_label
            if "input" in selector:
                return mock_inputs_locator
            mock = Mock(spec=Locator)
            mock.all.return_value = []
            mock.first = mock
            mock.count.return_value = 0
            mock.is_visible.return_value = False
            return mock

        mock_page.locator = Mock(side_effect=page_locator)
        mock_answer_engine.get_answer.return_value = "test@test.com"

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_text_inputs()

        mock_answer_engine.get_answer.assert_called_with("Email Address", "text")

    def test_extract_from_placeholder(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Extract question from placeholder attribute."""
        mock_input = create_mock_locator(placeholder="Enter your city")
        mock_page.locator.return_value.all.return_value = [mock_input]
        mock_answer_engine.get_answer.return_value = "New York"

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_text_inputs()

        mock_answer_engine.get_answer.assert_called_with("Enter your city", "text")


class TestEdgeCases:
    """Tests for edge cases."""

    def test_skip_already_filled_field(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Skip field that already has a value."""
        mock_input = create_mock_locator(aria_label="First Name", value="Existing Value")
        mock_page.locator.return_value.all.return_value = [mock_input]

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_text_inputs()

        mock_input.fill.assert_not_called()
        mock_answer_engine.get_answer.assert_not_called()

    def test_skip_hidden_field(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Skip hidden field."""
        mock_input = create_mock_locator(visible=False, aria_label="Hidden Field")
        mock_page.locator.return_value.all.return_value = [mock_input]

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_text_inputs()

        mock_input.fill.assert_not_called()

    def test_skip_disabled_field(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Skip disabled field."""
        mock_input = create_mock_locator(
            disabled=True, editable=False, aria_label="Disabled Field"
        )
        mock_page.locator.return_value.all.return_value = [mock_input]

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_text_inputs()

        mock_input.fill.assert_not_called()

    def test_no_visible_form_returns_success(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Return (True, []) when no visible form fields."""
        mock_page.locator.return_value.all.return_value = []

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        success, unknown = filler.fill_current_page()

        assert success is True
        assert unknown == []

    def test_multiple_forms_fills_all_visible(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Fill all visible fields across multiple forms."""
        mock_input1 = create_mock_locator(aria_label="First Name")
        mock_input2 = create_mock_locator(aria_label="Last Name")
        mock_page.locator.return_value.all.return_value = [mock_input1, mock_input2]
        mock_answer_engine.get_answer.return_value = "Test"

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        filler._fill_text_inputs()

        assert mock_input1.fill.called
        assert mock_input2.fill.called


class TestClickContinue:
    """Tests for click_continue method."""

    def test_click_continue_button(self, mock_page: Mock, mock_answer_engine: Mock) -> None:
        """Click continue button when visible."""
        mock_button = create_mock_locator()
        mock_button.is_visible.return_value = True
        mock_button.is_enabled.return_value = True

        mock_page.locator.return_value.first = mock_button

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        result = filler.click_continue()

        assert result is True
        mock_button.click.assert_called_once()

    def test_click_continue_no_button(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Return False when no continue button found."""
        mock_button = create_mock_locator(visible=False)
        mock_button.is_visible.side_effect = Exception("Not found")
        mock_page.locator.return_value.first = mock_button

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        result = filler.click_continue()

        assert result is False


class TestIsSuccessPage:
    """Tests for is_success_page method."""

    def test_success_page_detected(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Detect success page."""
        mock_indicator = create_mock_locator()
        mock_indicator.is_visible.return_value = True
        mock_page.locator.return_value.first = mock_indicator

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        result = filler.is_success_page()

        assert result is True

    def test_success_page_not_detected(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Return False when not on success page."""
        mock_indicator = create_mock_locator(visible=False)
        mock_indicator.is_visible.side_effect = Exception("Not found")
        mock_page.locator.return_value.first = mock_indicator

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        result = filler.is_success_page()

        assert result is False


class TestIsReviewPage:
    """Tests for is_review_page method."""

    def test_review_page_detected(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Detect review page."""
        mock_indicator = create_mock_locator()
        mock_indicator.is_visible.return_value = True
        mock_page.locator.return_value.first = mock_indicator

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        result = filler.is_review_page()

        assert result is True

    def test_review_page_not_detected(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Return False when not on review page."""
        mock_indicator = create_mock_locator(visible=False)
        mock_indicator.is_visible.side_effect = Exception("Not found")
        mock_page.locator.return_value.first = mock_indicator

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        result = filler.is_review_page()

        assert result is False


class TestUnknownQuestions:
    """Tests for unknown question logging."""

    def test_return_list_of_unknown_questions(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Return all unknown questions in list."""
        mock_input1 = create_mock_locator(aria_label="Unknown Question 1")
        mock_input2 = create_mock_locator(aria_label="Unknown Question 2")
        mock_page.locator.return_value.all.return_value = [mock_input1, mock_input2]
        mock_answer_engine.get_answer.return_value = None

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        success, unknown = filler.fill_current_page()

        assert success is False
        assert "Unknown Question 1" in unknown
        assert "Unknown Question 2" in unknown

    def test_unknown_questions_logged_for_later(
        self, mock_page: Mock, mock_answer_engine: Mock
    ) -> None:
        """Unknown questions are captured for config/answers.yaml update."""
        mock_input = create_mock_locator(aria_label="New Question Type")
        mock_page.locator.return_value.all.return_value = [mock_input]
        mock_answer_engine.get_answer.return_value = None

        filler = IndeedFormFiller(mock_page, mock_answer_engine)
        _, unknown = filler.fill_current_page()

        assert len(unknown) > 0
        assert "New Question Type" in unknown
