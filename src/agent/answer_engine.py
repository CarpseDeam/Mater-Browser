"""Deterministic answer engine for form questions."""
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ..feedback.failure_logger import FailureLogger, ApplicationFailure

logger = logging.getLogger(__name__)

_failure_logger = FailureLogger()


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

        # Experience confirmation patterns (Yes/No dropdowns) - MUST BE FIRST
        # These handle "Do you have at least X years of experience" type questions
        experience_confirmation_patterns = [
            (r"do you have at least.*years.*experience|at least.*years.*professional", "EXPERIENCE_CONFIRMATION", "yes"),
            (r"do you have.*\d+.*years", "EXPERIENCE_CONFIRMATION", "yes"),
            (r"software engineer.*experience|experience.*software engineer", "EXPERIENCE_CONFIRMATION", "yes"),
        ]

        for pattern_str, category, key in experience_confirmation_patterns:
            patterns.append((re.compile(pattern_str, re.IGNORECASE), category, key))

        # EEO patterns FIRST - must match before personal patterns to avoid
        # "Voluntary Self-Identification of Disability" matching personal.website
        eeo_patterns = [
            (r"self.?identification.*disability|voluntary.*disability|disability\s*status|disability|accommodation", "dropdowns", "disability_status"),
            (r"self.?identification.*veteran|voluntary.*veteran|veteran\s*status|protected\s*veteran|veteran", "dropdowns", "veteran_status"),
            (r"self.?identification.*gender|voluntary.*gender|gender\s*identity|gender|sex", "dropdowns", "gender"),
            (r"self.?identification.*race|voluntary.*race|race|ethnicity|racial\s*background", "dropdowns", "race"),
            (r"voluntary|self.?identification|demographic|eeo|equal\s*opportunity", "dropdowns", "decline_to_identify"),
        ]

        personal_patterns = [
            (r"first\s*name", "personal", "first_name"),
            (r"last\s*name", "personal", "last_name"),
            (r"email", "personal", "email"),
            (r"phone\s*country\s*code|country\s*code.*phone", "personal", "phone_country_code"),
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
            (r"will you.*need.*sponsorship|ever need.*sponsorship|sponsorship.*to work", "checkboxes", "require_visa"),
            (r"require.*employer.*sponsor|employer.*sponsored.*work.*authorization", "checkboxes", "require_visa"),
            (r"do you have.*experience|solid experience|experience with.*and knowledge", "checkboxes", "acknowledgment"),
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
            (r"designed.*application.*end\s*to\s*end|end\s*to\s*end.*application", "checkboxes", "designed_end_to_end"),
            (r"sms|text\s*(message|communication)", "checkboxes", "sms_consent"),
            (r"i\s*(understand|acknowledge|agree|certify|confirm)", "checkboxes", "acknowledgment"),
            (r"consent", "checkboxes", "general_consent"),
            # Common LinkedIn questions
            (r"can you start.*immediately|start.*urgent|urgently", "checkboxes", "start_immediately"),
            (r"comfortable.*remote|remote.*environment|work.*from.*home", "checkboxes", "remote_work"),
            (r"felony|convicted|criminal.*record", "checkboxes", "background_check"),
            (r"previously.*worked.*at|former.*employee|worked.*here.*before", "checkboxes", "worked_here_before"),
            (r"completed.*education|bachelor|master|degree.*completed|level.*education", "checkboxes", "education_completed"),
        ]

        experience_patterns = [
            # Generic work experience
            (r"how many years.*(work|professional).*experience|years of work experience|total.*experience", "industry", "software_engineering"),
            # Tech-specific
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

        salary_patterns = [
            (r"salary\s*expectation|desired\s*salary|expected\s*compensation", "salary", "expected"),
            (r"minimum\s*salary|salary\s*requirement", "salary", "minimum"),
            (r"hourly\s*rate|rate\s*expectation", "salary", "hourly_rate"),
        ]

        language_patterns = [
            (r"english\s*proficiency|english\s*fluency|language\s*proficiency", "languages", "english"),
        ]

        preference_patterns = [
            (r"notice\s*period|how\s*much\s*notice|when\s*can\s*you\s*start", "preferences", "notice_period"),
            (r"available\s*to\s*start|start\s*date|earliest\s*start", "preferences", "available_start"),
            (r"work\s*type|remote.?hybrid.?onsite", "preferences", "work_type"),
            (r"which\s*database|database.*experienced|experienced.*database", "preferences", "databases"),
        ]

        # Yes/No dropdown patterns (consent, agreements, confirmations)
        yes_no_dropdown_patterns = [
            (r"agree.*privacy\s*policy|privacy\s*policy.*data\s*processing|clicking.*yes.*agree", "yes_no", "yes"),
            (r"accurate\s*information|dishonesty.*rejection|termination", "yes_no", "yes"),
            (r"certify.*true|information.*accurate|truthful", "yes_no", "yes"),
        ]

        all_patterns = (
            eeo_patterns
            + personal_patterns
            + checkbox_patterns
            + experience_patterns
            + salary_patterns
            + language_patterns
            + preference_patterns
            + yes_no_dropdown_patterns
        )

        for pattern_str, category, key in all_patterns:
            patterns.append((re.compile(pattern_str, re.IGNORECASE), category, key))

        return patterns

    def get_answer(
        self,
        question: str,
        field_type: str = "text",
        *,
        job_url: str = "",
        job_title: str = "",
        company: str = "",
        page_snapshot: str | None = None,
    ) -> Any | None:
        """Look up answer for a question.

        Args:
            question: The question text (label, placeholder, aria-label)
            field_type: Type of field (text, checkbox, select, radio, number)
            job_url: URL of the job posting (for failure logging)
            job_title: Title of the job (for failure logging)
            company: Company name (for failure logging)
            page_snapshot: HTML snapshot of the page (for failure logging)

        Returns:
            Answer value or None if no match found
        """
        question_lower = question.lower().strip()

        # FIRST: Check for experience dropdown questions (Yes/No and years)
        if field_type == "select":
            exp_answer = self._get_experience_dropdown_answer(question, field_type)
            if exp_answer is not None:
                logger.info(f"AnswerEngine: '{question[:50]}' -> experience_dropdown = {exp_answer}")
                return exp_answer

        for pattern, category, key in self._question_patterns:
            if pattern.search(question_lower):
                # Special handling for experience confirmation patterns
                if category == "EXPERIENCE_CONFIRMATION":
                    logger.info(f"AnswerEngine: '{question[:50]}' -> experience_confirmation = Yes")
                    return "Yes"
                value = self._config.get(category, {}).get(key)
                if value is not None:
                    logger.info(f"AnswerEngine: '{question[:50]}' -> {category}.{key} = {value}")
                    return self._format_answer(value, field_type)

        experience_match = self._match_experience_question(question_lower)
        if experience_match is not None:
            return self._format_answer(experience_match, field_type)

        logger.warning(f"AnswerEngine: No match for '{question[:80]}'")
        self._log_unknown_question(question, field_type, job_url, job_title, company, page_snapshot)
        return None

    def _log_unknown_question(
        self,
        question: str,
        field_type: str,
        job_url: str,
        job_title: str,
        company: str,
        page_snapshot: str | None,
    ) -> None:
        """Log an unknown question failure."""
        truncated_snapshot = None
        if page_snapshot is not None:
            truncated_snapshot = page_snapshot[:50 * 1024] if len(page_snapshot) > 50 * 1024 else page_snapshot

        failure = ApplicationFailure(
            timestamp=datetime.now().isoformat(),
            job_url=job_url,
            job_title=job_title,
            company=company,
            failure_type="unknown_question",
            details={"question": question, "field_type": field_type},
            page_snapshot=truncated_snapshot,
        )
        try:
            _failure_logger.log(failure)
        except Exception as e:
            logger.debug(f"Failed to log unknown question: {e}")

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

    def _match_multi_tech_experience(self, question: str) -> int | None:
        """Match questions asking about experience with multiple technologies.

        E.g., "How many years using Go, Python, or comparable language?"
        Returns the maximum experience from any mentioned technology.
        """
        tech_keywords = {
            "python": "python",
            "go": "go",
            "golang": "go",
            "java": "java",
            "c#": "csharp",
            "csharp": "csharp",
            "ruby": "ruby",
            "rust": "rust",
            "scala": "scala",
            "javascript": "javascript",
            "typescript": "typescript",
            "sql": "sql",
            "postgresql": "postgresql",
            "postgres": "postgresql",
            "mysql": "sql",
            "database": "postgresql",
            "relational": "postgresql",
        }

        tech_config = self._config.get("technology", {})
        max_exp = 0
        matched_any = False

        question_lower = question.lower()
        for keyword, config_key in tech_keywords.items():
            if keyword in question_lower:
                exp = tech_config.get(config_key, 0)
                if exp > max_exp:
                    max_exp = exp
                    matched_any = True

        return max_exp if matched_any else None

    def _get_experience_dropdown_answer(self, question: str, field_type: str) -> str | None:
        """Get answer for experience-related dropdown questions.

        Handles:
        - "Do you have at least X years" → "Yes"
        - "How many years of experience" → numeric string for form filler to match
        """
        q_lower = question.lower()

        # Yes/No experience confirmation
        if "do you have" in q_lower and "years" in q_lower:
            return "Yes"

        # Years of experience - return the numeric value
        multi_tech = self._match_multi_tech_experience(question)
        if multi_tech is not None:
            return str(multi_tech)

        return None

    def _format_answer(self, value: Any, field_type: str) -> Any:
        """Format answer for field type."""
        if field_type == "checkbox":
            return bool(value)
        if field_type == "number":
            return int(value) if isinstance(value, (int, float)) else 0
        if field_type == "radio" and isinstance(value, bool):
            return "Yes" if value else "No"
        if field_type == "select":
            return str(value)
        return str(value)

    def has_answer(self, question: str) -> bool:
        """Check if we have an answer for this question."""
        return self.get_answer(question) is not None
