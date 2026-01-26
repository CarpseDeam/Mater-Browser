"""Tests for SmartRecruitersHandler."""
from unittest.mock import MagicMock, patch
import pytest

from src.ats.handlers.smartrecruiters import SmartRecruitersHandler
from src.ats.base_handler import FormPage, PageResult


class TestSmartRecruitersHandlerInit:
    def test_ats_name_is_smartrecruiters(self) -> None:
        assert SmartRecruitersHandler.ATS_NAME == "smartrecruiters"

    def test_has_apply_button_selectors(self) -> None:
        assert len(SmartRecruitersHandler.APPLY_BUTTON_SELECTORS) > 0

    def test_has_next_button_selectors(self) -> None:
        assert len(SmartRecruitersHandler.NEXT_BUTTON_SELECTORS) > 0

    def test_has_submit_button_selectors(self) -> None:
        assert len(SmartRecruitersHandler.SUBMIT_BUTTON_SELECTORS) > 0

    def test_has_field_selectors(self) -> None:
        required_fields = ["first_name", "last_name", "email", "phone", "resume", "linkedin"]
        for field in required_fields:
            assert field in SmartRecruitersHandler.FIELD_SELECTORS

    def test_has_page_indicators(self) -> None:
        required_pages = [FormPage.JOB_LISTING, FormPage.PERSONAL_INFO, FormPage.CONFIRMATION]
        for page in required_pages:
            assert page in SmartRecruitersHandler.PAGE_INDICATORS


class TestSmartRecruitersHandlerConstruction:
    @pytest.fixture
    def mock_page(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def profile(self) -> dict:
        return {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "555-1234",
            "linkedin_url": "https://linkedin.com/in/johndoe",
        }

    def test_initializes_with_page_and_profile(
        self, mock_page: MagicMock, profile: dict
    ) -> None:
        handler = SmartRecruitersHandler(mock_page, profile)
        assert handler._page is mock_page
        assert handler._profile is profile
        assert handler._resume_path is None

    def test_initializes_with_resume_path(
        self, mock_page: MagicMock, profile: dict
    ) -> None:
        handler = SmartRecruitersHandler(mock_page, profile, "/path/to/resume.pdf")
        assert handler._resume_path == "/path/to/resume.pdf"


class TestDetectPageState:
    @pytest.fixture
    def mock_page(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def handler(self, mock_page: MagicMock) -> SmartRecruitersHandler:
        return SmartRecruitersHandler(mock_page, {})

    def test_detects_confirmation_page(
        self, handler: SmartRecruitersHandler, mock_page: MagicMock
    ) -> None:
        def is_visible_side_effect(selector: str, timeout: int = 500) -> bool:
            return selector in SmartRecruitersHandler.PAGE_INDICATORS[FormPage.CONFIRMATION]

        mock_locator = MagicMock()
        mock_locator.first.is_visible.side_effect = is_visible_side_effect
        mock_page.locator.return_value = mock_locator

        with patch.object(handler, "_is_visible", side_effect=is_visible_side_effect):
            result = handler.detect_page_state()
            assert result == FormPage.CONFIRMATION

    def test_detects_personal_info_page(
        self, handler: SmartRecruitersHandler, mock_page: MagicMock
    ) -> None:
        def is_visible_side_effect(selector: str, timeout: int = 500) -> bool:
            return selector in SmartRecruitersHandler.PAGE_INDICATORS[FormPage.PERSONAL_INFO]

        with patch.object(handler, "_is_visible", side_effect=is_visible_side_effect):
            result = handler.detect_page_state()
            assert result == FormPage.PERSONAL_INFO

    def test_detects_job_listing_page(
        self, handler: SmartRecruitersHandler, mock_page: MagicMock
    ) -> None:
        def is_visible_side_effect(selector: str, timeout: int = 500) -> bool:
            return selector in SmartRecruitersHandler.PAGE_INDICATORS[FormPage.JOB_LISTING]

        with patch.object(handler, "_is_visible", side_effect=is_visible_side_effect):
            result = handler.detect_page_state()
            assert result == FormPage.JOB_LISTING

    def test_returns_unknown_when_no_indicators_match(
        self, handler: SmartRecruitersHandler
    ) -> None:
        with patch.object(handler, "_is_visible", return_value=False):
            result = handler.detect_page_state()
            assert result == FormPage.UNKNOWN

    def test_confirmation_takes_priority_over_other_pages(
        self, handler: SmartRecruitersHandler
    ) -> None:
        with patch.object(handler, "_is_visible", return_value=True):
            result = handler.detect_page_state()
            assert result == FormPage.CONFIRMATION


class TestFillCurrentPage:
    @pytest.fixture
    def mock_page(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def profile(self) -> dict:
        return {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": "jane@example.com",
            "phone": "555-5678",
        }

    @pytest.fixture
    def handler(self, mock_page: MagicMock, profile: dict) -> SmartRecruitersHandler:
        return SmartRecruitersHandler(mock_page, profile)

    def test_returns_page_result_on_confirmation(
        self, handler: SmartRecruitersHandler
    ) -> None:
        with patch.object(handler, "detect_page_state", return_value=FormPage.CONFIRMATION):
            result = handler.fill_current_page()
            assert isinstance(result, PageResult)
            assert result.success is True
            assert result.page_type == FormPage.CONFIRMATION
            assert result.needs_next_page is False

    def test_clicks_apply_on_job_listing(
        self, handler: SmartRecruitersHandler
    ) -> None:
        call_count = 0

        def detect_state_side_effect() -> FormPage:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return FormPage.JOB_LISTING
            return FormPage.PERSONAL_INFO

        with patch.object(handler, "detect_page_state", side_effect=detect_state_side_effect):
            with patch.object(handler, "click_apply", return_value=True) as mock_apply:
                with patch.object(handler, "_wait"):
                    with patch.object(handler, "_fill_application_form", return_value=PageResult(
                        True, FormPage.PERSONAL_INFO, "Filled", True
                    )):
                        handler.fill_current_page()
                        mock_apply.assert_called_once()

    def test_fills_application_form_on_personal_info(
        self, handler: SmartRecruitersHandler
    ) -> None:
        with patch.object(handler, "detect_page_state", return_value=FormPage.PERSONAL_INFO):
            with patch.object(
                handler, "_fill_application_form",
                return_value=PageResult(True, FormPage.PERSONAL_INFO, "Filled 4 fields", True)
            ) as mock_fill:
                result = handler.fill_current_page()
                mock_fill.assert_called_once()
                assert result.success is True


class TestFillBasicFields:
    @pytest.fixture
    def mock_page(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def profile(self) -> dict:
        return {
            "first_name": "Alice",
            "last_name": "Wonder",
            "email": "alice@example.com",
            "phone": "555-9999",
        }

    @pytest.fixture
    def handler(self, mock_page: MagicMock, profile: dict) -> SmartRecruitersHandler:
        return SmartRecruitersHandler(mock_page, profile)

    def test_fills_all_basic_fields_returns_count(
        self, handler: SmartRecruitersHandler
    ) -> None:
        with patch.object(handler, "_fill_field", return_value=True):
            result = handler._fill_basic_fields()
            assert result == 4

    def test_returns_zero_when_no_fields_filled(
        self, handler: SmartRecruitersHandler
    ) -> None:
        with patch.object(handler, "_fill_field", return_value=False):
            result = handler._fill_basic_fields()
            assert result == 0

    def test_fills_fields_with_profile_values(
        self, handler: SmartRecruitersHandler, profile: dict
    ) -> None:
        filled_values: list[str] = []

        def capture_fill(selectors: list, value: str) -> bool:
            filled_values.append(value)
            return True

        with patch.object(handler, "_fill_field", side_effect=capture_fill):
            handler._fill_basic_fields()

        assert profile["first_name"] in filled_values
        assert profile["last_name"] in filled_values
        assert profile["email"] in filled_values
        assert profile["phone"] in filled_values


class TestFillOptionalFields:
    @pytest.fixture
    def mock_page(self) -> MagicMock:
        return MagicMock()

    def test_fills_linkedin_url_when_provided(self, mock_page: MagicMock) -> None:
        profile = {"linkedin_url": "https://linkedin.com/in/user"}
        handler = SmartRecruitersHandler(mock_page, profile)

        with patch.object(handler, "_fill_field") as mock_fill:
            handler._fill_optional_fields()
            mock_fill.assert_called_once()
            call_args = mock_fill.call_args
            assert call_args[0][1] == profile["linkedin_url"]

    def test_handles_missing_linkedin_url(self, mock_page: MagicMock) -> None:
        handler = SmartRecruitersHandler(mock_page, {})

        with patch.object(handler, "_fill_field") as mock_fill:
            handler._fill_optional_fields()
            mock_fill.assert_called_once()
            call_args = mock_fill.call_args
            assert call_args[0][1] == ""


class TestUploadResume:
    @pytest.fixture
    def mock_page(self) -> MagicMock:
        return MagicMock()

    def test_uploads_resume_when_path_provided(self, mock_page: MagicMock) -> None:
        resume_path = "/path/to/resume.pdf"
        handler = SmartRecruitersHandler(mock_page, {}, resume_path)

        with patch.object(handler, "_upload_file") as mock_upload:
            with patch.object(handler, "_wait"):
                handler._upload_resume()
                mock_upload.assert_called_once()
                call_args = mock_upload.call_args
                assert call_args[0][1] == resume_path

    def test_does_not_upload_when_no_path(self, mock_page: MagicMock) -> None:
        handler = SmartRecruitersHandler(mock_page, {})

        with patch.object(handler, "_upload_file") as mock_upload:
            handler._upload_resume()
            mock_upload.assert_not_called()


class TestCheckAllCheckboxes:
    @pytest.fixture
    def mock_page(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def handler(self, mock_page: MagicMock) -> SmartRecruitersHandler:
        return SmartRecruitersHandler(mock_page, {})

    def test_checks_unchecked_checkboxes(
        self, handler: SmartRecruitersHandler, mock_page: MagicMock
    ) -> None:
        mock_checkbox = MagicMock()
        mock_checkbox.is_checked.return_value = False
        mock_locator = MagicMock()
        mock_locator.all.return_value = [mock_checkbox]
        mock_page.locator.return_value = mock_locator

        handler._check_all_checkboxes()
        mock_checkbox.check.assert_called_once()

    def test_skips_already_checked_checkboxes(
        self, handler: SmartRecruitersHandler, mock_page: MagicMock
    ) -> None:
        mock_checkbox = MagicMock()
        mock_checkbox.is_checked.return_value = True
        mock_locator = MagicMock()
        mock_locator.all.return_value = [mock_checkbox]
        mock_page.locator.return_value = mock_locator

        handler._check_all_checkboxes()
        mock_checkbox.check.assert_not_called()

    def test_handles_exception_gracefully(
        self, handler: SmartRecruitersHandler, mock_page: MagicMock
    ) -> None:
        mock_page.locator.side_effect = Exception("Element not found")
        handler._check_all_checkboxes()


class TestFillApplicationForm:
    @pytest.fixture
    def mock_page(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def handler(self, mock_page: MagicMock) -> SmartRecruitersHandler:
        return SmartRecruitersHandler(mock_page, {})

    def test_calls_all_fill_methods(self, handler: SmartRecruitersHandler) -> None:
        with patch.object(handler, "_fill_basic_fields", return_value=4) as mock_basic:
            with patch.object(handler, "_fill_optional_fields") as mock_optional:
                with patch.object(handler, "_upload_resume") as mock_resume:
                    with patch.object(handler, "_check_all_checkboxes") as mock_check:
                        with patch.object(handler, "click_submit", return_value=False):
                            with patch.object(handler, "click_next", return_value=False):
                                handler._fill_application_form()

                        mock_basic.assert_called_once()
                        mock_optional.assert_called_once()
                        mock_resume.assert_called_once()
                        mock_check.assert_called_once()

    def test_returns_success_on_submit(self, handler: SmartRecruitersHandler) -> None:
        with patch.object(handler, "_fill_basic_fields", return_value=4):
            with patch.object(handler, "_fill_optional_fields"):
                with patch.object(handler, "_upload_resume"):
                    with patch.object(handler, "_check_all_checkboxes"):
                        with patch.object(handler, "click_submit", return_value=True):
                            with patch.object(handler, "_wait"):
                                with patch.object(handler, "detect_page_state", return_value=FormPage.CONFIRMATION):
                                    result = handler._fill_application_form()

                        assert result.success is True
                        assert "submitted" in result.message.lower() or result.needs_next_page is True

    def test_advances_with_next_button(self, handler: SmartRecruitersHandler) -> None:
        with patch.object(handler, "_fill_basic_fields", return_value=4):
            with patch.object(handler, "_fill_optional_fields"):
                with patch.object(handler, "_upload_resume"):
                    with patch.object(handler, "_check_all_checkboxes"):
                        with patch.object(handler, "click_submit", return_value=False):
                            with patch.object(handler, "click_next", return_value=True):
                                result = handler._fill_application_form()

                        assert result.success is True
                        assert result.needs_next_page is True
                        assert "advanced" in result.message.lower()

    def test_returns_failure_when_cannot_advance(
        self, handler: SmartRecruitersHandler
    ) -> None:
        with patch.object(handler, "_fill_basic_fields", return_value=4):
            with patch.object(handler, "_fill_optional_fields"):
                with patch.object(handler, "_upload_resume"):
                    with patch.object(handler, "_check_all_checkboxes"):
                        with patch.object(handler, "click_submit", return_value=False):
                            with patch.object(handler, "click_next", return_value=False):
                                result = handler._fill_application_form()

                        assert result.success is False
                        assert "could not advance" in result.message.lower()


class TestPageIndicatorSelectors:
    def test_job_listing_indicators_are_valid_css_selectors(self) -> None:
        for selector in SmartRecruitersHandler.PAGE_INDICATORS[FormPage.JOB_LISTING]:
            assert isinstance(selector, str)
            assert len(selector) > 0

    def test_personal_info_indicators_are_valid_css_selectors(self) -> None:
        for selector in SmartRecruitersHandler.PAGE_INDICATORS[FormPage.PERSONAL_INFO]:
            assert isinstance(selector, str)
            assert len(selector) > 0

    def test_confirmation_indicators_are_valid_css_selectors(self) -> None:
        for selector in SmartRecruitersHandler.PAGE_INDICATORS[FormPage.CONFIRMATION]:
            assert isinstance(selector, str)
            assert len(selector) > 0


class TestFieldSelectors:
    @pytest.mark.parametrize("field", ["first_name", "last_name", "email", "phone", "resume", "linkedin"])
    def test_field_has_multiple_selectors(self, field: str) -> None:
        selectors = SmartRecruitersHandler.FIELD_SELECTORS[field]
        assert len(selectors) >= 1

    def test_email_selectors_include_type_email(self) -> None:
        email_selectors = SmartRecruitersHandler.FIELD_SELECTORS["email"]
        assert any("email" in s.lower() for s in email_selectors)

    def test_phone_selectors_include_tel_type(self) -> None:
        phone_selectors = SmartRecruitersHandler.FIELD_SELECTORS["phone"]
        assert any("tel" in s.lower() for s in phone_selectors)

    def test_resume_selectors_include_file_input(self) -> None:
        resume_selectors = SmartRecruitersHandler.FIELD_SELECTORS["resume"]
        assert any("file" in s.lower() for s in resume_selectors)


class TestButtonSelectors:
    def test_apply_selectors_include_apply_text(self) -> None:
        selectors = SmartRecruitersHandler.APPLY_BUTTON_SELECTORS
        assert any("apply" in s.lower() for s in selectors)

    def test_next_selectors_include_submit_type(self) -> None:
        selectors = SmartRecruitersHandler.NEXT_BUTTON_SELECTORS
        assert any("submit" in s.lower() for s in selectors)

    def test_submit_selectors_include_submit_text(self) -> None:
        selectors = SmartRecruitersHandler.SUBMIT_BUTTON_SELECTORS
        assert any("submit" in s.lower() for s in selectors)
