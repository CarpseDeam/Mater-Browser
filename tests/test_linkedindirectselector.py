"""Tests for LinkedIn direct selector in PageClassifier."""
import pytest
from unittest.mock import MagicMock, patch

from src.agent.page_classifier import PageClassifier, LINKEDIN_EASY_APPLY_SELECTORS


@pytest.fixture
def mock_page() -> MagicMock:
    page = MagicMock()
    page.url = "https://linkedin.com/jobs/view/123"
    page.content.return_value = "<html><body></body></html>"
    return page


@pytest.fixture
def classifier(mock_page: MagicMock) -> PageClassifier:
    return PageClassifier(mock_page)


class TestLinkedInDirectSelector:
    def test_try_linkedin_direct_returns_candidate_when_selector_matches(
        self, classifier: PageClassifier, mock_page: MagicMock
    ) -> None:
        locator = MagicMock()
        locator.is_visible.return_value = True
        locator.text_content.return_value = "Easy Apply"
        locator.get_attribute.side_effect = lambda attr: {
            "aria-label": "Easy Apply to Software Engineer",
            "data-testid": "jobs-apply-button",
        }.get(attr)
        mock_page.locator.return_value.first = locator

        result = classifier._try_linkedin_direct()

        assert result is not None
        assert result.text == "Easy Apply"
        assert result.is_visible is True
        assert result.selector == LINKEDIN_EASY_APPLY_SELECTORS[0]

    def test_try_linkedin_direct_tries_selectors_in_order(
        self, classifier: PageClassifier, mock_page: MagicMock
    ) -> None:
        call_count = 0
        matched_selector = LINKEDIN_EASY_APPLY_SELECTORS[2]

        def selector_side_effect(selector: str) -> MagicMock:
            nonlocal call_count
            locator = MagicMock()
            if selector == matched_selector:
                locator.is_visible.return_value = True
                locator.text_content.return_value = "Easy Apply"
                locator.get_attribute.return_value = None
            else:
                locator.is_visible.return_value = False
            call_count += 1
            return MagicMock(first=locator)

        mock_page.locator.side_effect = selector_side_effect

        result = classifier._try_linkedin_direct()

        assert result is not None
        assert result.selector == matched_selector

    def test_find_apply_button_calls_direct_first_before_generic(
        self, classifier: PageClassifier, mock_page: MagicMock
    ) -> None:
        locator = MagicMock()
        locator.is_visible.return_value = True
        locator.text_content.return_value = "Easy Apply"
        locator.get_attribute.return_value = None
        mock_page.locator.return_value.first = locator

        with patch.object(classifier._dom_extractor, 'extract_candidates') as mock_extract:
            result = classifier.find_apply_button()

            mock_extract.assert_not_called()
            assert result is not None
            assert result.text == "Easy Apply"

    def test_find_apply_button_falls_back_to_generic_when_no_direct_match(
        self, classifier: PageClassifier, mock_page: MagicMock
    ) -> None:
        locator = MagicMock()
        locator.is_visible.return_value = False
        mock_page.locator.return_value.first = locator

        with patch.object(classifier._dom_extractor, 'extract_candidates') as mock_extract:
            from src.agent.dom_extractor import ElementCandidate
            mock_extract.return_value = [
                ElementCandidate(
                    selector='button:text-is("Apply")',
                    tag="button",
                    text="Apply",
                    role="button",
                    aria_label=None,
                    href=None,
                    data_testid=None,
                    is_visible=True,
                )
            ]

            result = classifier.find_apply_button()

            mock_extract.assert_called_once()
            assert result is not None
            assert result.text == "Apply"

    def test_direct_selector_builds_element_candidate_correctly(
        self, classifier: PageClassifier, mock_page: MagicMock
    ) -> None:
        locator = MagicMock()
        locator.is_visible.return_value = True
        locator.text_content.return_value = "  Easy Apply  "
        locator.get_attribute.side_effect = lambda attr: {
            "aria-label": "Easy Apply to Job",
            "data-testid": "test-id",
        }.get(attr)
        mock_page.locator.return_value.first = locator

        result = classifier._try_linkedin_direct()

        assert result is not None
        assert result.tag == "button"
        assert result.text == "Easy Apply"
        assert result.role == "button"
        assert result.aria_label == "Easy Apply to Job"
        assert result.data_testid == "test-id"
        assert result.href is None
        assert result.is_visible is True
        assert result.score == 10.0
