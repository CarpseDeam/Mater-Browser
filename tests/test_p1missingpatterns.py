"""Tests for P1MissingPatterns - EEO, salary, language, and preference patterns."""
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.agent.answer_engine import AnswerEngine


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Create a temporary config file with test data."""
    config = {
        "dropdowns": {
            "gender": "Male",
            "race": "Asian",
            "ethnicity": "Asian",
            "veteran_status": "I am not a protected veteran",
            "disability_status": "No, I don't have a disability",
        },
        "salary": {
            "expected": "120000",
            "minimum": "100000",
            "hourly_rate": "60",
        },
        "languages": {
            "english": "Native",
        },
        "preferences": {
            "notice_period": "2 weeks",
            "available_start": "Immediately",
            "work_type": "Remote",
        },
    }
    config_file = tmp_path / "answers.yaml"
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(config, f)
    return config_file


@pytest.fixture
def engine(config_path: Path) -> AnswerEngine:
    """Create an AnswerEngine with test config."""
    return AnswerEngine(config_path)


class TestEEOPatterns:
    """Tests for EEO/demographic question patterns."""

    @pytest.mark.parametrize(
        "question,expected_value",
        [
            ("What is your gender?", "Male"),
            ("Gender identity", "Male"),
            ("Sex", "Male"),
        ],
    )
    def test_gender_patterns(
        self, engine: AnswerEngine, question: str, expected_value: str
    ) -> None:
        result = engine.get_answer(question)
        assert result == expected_value

    @pytest.mark.parametrize(
        "question",
        [
            "What is your race?",
            "Ethnicity",
            "What is your racial background?",
        ],
    )
    def test_race_ethnicity_patterns(self, engine: AnswerEngine, question: str) -> None:
        result = engine.get_answer(question)
        assert result == "Asian"

    @pytest.mark.parametrize(
        "question",
        [
            "Veteran status",
            "Are you a protected veteran?",
            "Veteran",
        ],
    )
    def test_veteran_patterns(self, engine: AnswerEngine, question: str) -> None:
        result = engine.get_answer(question)
        assert result == "I am not a protected veteran"

    @pytest.mark.parametrize(
        "question",
        [
            "Disability status",
            "Do you have a disability?",
            "Do you need accommodation?",
        ],
    )
    def test_disability_patterns(self, engine: AnswerEngine, question: str) -> None:
        result = engine.get_answer(question)
        assert result == "No, I don't have a disability"


class TestSalaryPatterns:
    """Tests for salary question patterns."""

    @pytest.mark.parametrize(
        "question",
        [
            "What is your salary expectation?",
            "Desired salary",
            "Expected compensation",
        ],
    )
    def test_expected_salary_patterns(
        self, engine: AnswerEngine, question: str
    ) -> None:
        result = engine.get_answer(question)
        assert result == "120000"

    @pytest.mark.parametrize(
        "question",
        [
            "What is your minimum salary?",
            "Salary requirement",
        ],
    )
    def test_minimum_salary_patterns(
        self, engine: AnswerEngine, question: str
    ) -> None:
        result = engine.get_answer(question)
        assert result == "100000"

    @pytest.mark.parametrize(
        "question",
        [
            "What is your hourly rate?",
            "Rate expectation",
        ],
    )
    def test_hourly_rate_patterns(self, engine: AnswerEngine, question: str) -> None:
        result = engine.get_answer(question)
        assert result == "60"


class TestLanguagePatterns:
    """Tests for language question patterns."""

    @pytest.mark.parametrize(
        "question",
        [
            "English proficiency",
            "English fluency",
            "Language proficiency",
        ],
    )
    def test_language_patterns(self, engine: AnswerEngine, question: str) -> None:
        result = engine.get_answer(question)
        assert result == "Native"


class TestPreferencePatterns:
    """Tests for preference question patterns."""

    @pytest.mark.parametrize(
        "question",
        [
            "What is your notice period?",
            "How much notice do you need to give?",
            "When can you start?",
        ],
    )
    def test_notice_period_patterns(self, engine: AnswerEngine, question: str) -> None:
        result = engine.get_answer(question)
        assert result == "2 weeks"

    @pytest.mark.parametrize(
        "question",
        [
            "When are you available to start?",
            "Start date",
            "What is your earliest start date?",
        ],
    )
    def test_available_start_patterns(
        self, engine: AnswerEngine, question: str
    ) -> None:
        result = engine.get_answer(question)
        assert result == "Immediately"

    @pytest.mark.parametrize(
        "question",
        [
            "Work type preference",
            "Remote/hybrid/onsite",
        ],
    )
    def test_work_type_patterns(self, engine: AnswerEngine, question: str) -> None:
        result = engine.get_answer(question)
        assert result == "Remote"


class TestSelectFieldHandling:
    """Tests for select/dropdown field type handling."""

    def test_select_field_returns_string(self, engine: AnswerEngine) -> None:
        result = engine.get_answer("What is your gender?", field_type="select")
        assert result == "Male"
        assert isinstance(result, str)

    def test_select_field_with_numeric_value(self, engine: AnswerEngine) -> None:
        result = engine.get_answer("Salary expectation", field_type="select")
        assert result == "120000"
        assert isinstance(result, str)
