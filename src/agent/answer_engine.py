"""Deterministic answer engine for form questions."""
import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class AnswerEngine:
    """Config-driven answer lookup for LinkedIn Easy Apply questions."""

    def __init__(self, config_path: Path | None = None) -> None:
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "answers.yaml"
        self._config = self._load_config(config_path)
        self._question_patterns = self._build_patterns()

    def _load_config(self, path: Path) -> dict:
        """Load answer configuration from YAML."""
        if not path.exists():
            logger.warning(f"Answer config not found: {path}")
            return {}
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _build_patterns(self) -> list[tuple[re.Pattern, str, str]]:
        """Build regex patterns for question matching.

        Returns list of (pattern, category, key) tuples.
        """
        patterns = []

        personal_patterns = [
            (r"first\s*name", "personal", "first_name"),
            (r"last\s*name", "personal", "last_name"),
            (r"email", "personal", "email"),
            (r"phone|mobile|cell", "personal", "phone"),
            (r"city|location", "personal", "city"),
            (r"state|province", "personal", "state"),
            (r"zip|postal", "personal", "zip"),
            (r"linkedin", "personal", "linkedin"),
            (r"website|portfolio|github", "personal", "website"),
        ]

        checkbox_patterns = [
            (r"driver.?s?\s*licen[sc]e", "checkboxes", "drivers_license"),
            (r"(require|need)\s*(visa|sponsorship)", "checkboxes", "require_visa"),
            (r"legally\s*(authorized|able)", "checkboxes", "legally_authorized"),
            (r"(willing|open)\s*to\s*relocate", "checkboxes", "willing_to_relocate"),
            (r"background\s*check", "checkboxes", "background_check"),
            (r"drug\s*(test|screen)", "checkboxes", "drug_test"),
            (r"start\s*(immediately|right\s*away|asap)", "checkboxes", "start_immediately"),
            (r"(comfortable|able)\s*(commuting|to\s*commute)", "checkboxes", "comfortable_commuting"),
            (r"remote\s*(work|position)", "checkboxes", "remote_work"),
            (r"(us|u\.s\.?|united\s*states)\s*citizen", "checkboxes", "us_citizen"),
            (r"(authorized|eligible)\s*to\s*work", "checkboxes", "work_authorization"),
            (r"(18|eighteen)\s*(years|yrs)\s*(old|of\s*age|or\s*older)", "checkboxes", "over_18"),
        ]

        experience_patterns = [
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*python", "technology", "python"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*fastapi", "technology", "fastapi"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*(aws|amazon)", "technology", "aws"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*docker", "technology", "docker"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*kubernetes", "technology", "kubernetes"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*(postgres|postgresql)", "technology", "postgresql"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*sql", "technology", "sql"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*javascript", "technology", "javascript"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*typescript", "technology", "typescript"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*react", "technology", "react"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*git", "technology", "git"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*linux", "technology", "linux"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*redis", "technology", "redis"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*snowflake", "technology", "snowflake"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*pydantic", "technology", "pydantic"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*sqlalchemy", "technology", "sqlalchemy"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*asyncio", "technology", "asyncio"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*selenium", "technology", "selenium"),
            (r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*pytest", "technology", "pytest"),
        ]

        for pattern_str, category, key in personal_patterns + checkbox_patterns + experience_patterns:
            patterns.append((re.compile(pattern_str, re.IGNORECASE), category, key))

        return patterns

    def get_answer(self, question: str, field_type: str = "text") -> Any | None:
        """Look up answer for a question.

        Args:
            question: The question text (label, placeholder, aria-label)
            field_type: Type of field (text, checkbox, select, radio, number)

        Returns:
            Answer value or None if no match found
        """
        question_lower = question.lower().strip()

        for pattern, category, key in self._question_patterns:
            if pattern.search(question_lower):
                value = self._config.get(category, {}).get(key)
                if value is not None:
                    logger.info(f"AnswerEngine: '{question[:50]}' -> {category}.{key} = {value}")
                    return self._format_answer(value, field_type)

        experience_match = self._match_experience_question(question_lower)
        if experience_match is not None:
            return self._format_answer(experience_match, field_type)

        logger.warning(f"AnswerEngine: No match for '{question[:80]}'")
        return None

    def _match_experience_question(self, question: str) -> int | None:
        """Try to match 'years of X experience' questions dynamically."""
        exp_pattern = r"years?\s*(of)?\s*(experience|exp)?\s*(with|in|using)?\s*(\w+)"
        match = re.search(exp_pattern, question)
        if not match:
            return None

        skill = match.group(4).lower()

        tech_config = self._config.get("technology", {})
        if skill in tech_config:
            return tech_config[skill]

        industry_config = self._config.get("industry", {})
        if skill in industry_config:
            return industry_config[skill]

        return tech_config.get("default", 0)

    def _format_answer(self, value: Any, field_type: str) -> Any:
        """Format answer for field type."""
        if field_type == "checkbox":
            return bool(value)
        if field_type == "number":
            return int(value) if isinstance(value, (int, float)) else 0
        if field_type == "radio" and isinstance(value, bool):
            return "Yes" if value else "No"
        return str(value)

    def has_answer(self, question: str) -> bool:
        """Check if we have an answer for this question."""
        return self.get_answer(question) is not None
