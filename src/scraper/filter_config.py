"""Centralized job filtering configuration."""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

import logging

logger = logging.getLogger(__name__)


class RuleType(Enum):
    """Types of filter rules for categorizing rejections."""

    TITLE_EXCLUSION = "title_exclusion"
    BLOCKED_DOMAIN = "blocked_domain"
    BLOCKED_URL_PATTERN = "blocked_url_pattern"
    DESCRIPTION_EXCLUSION = "description_exclusion"
    STACK_EXCLUSION = "stack_exclusion"
    ROLE_EXCLUSION = "role_exclusion"
    LOCATION_EXCLUSION = "location_exclusion"
    MISSING_KEYWORD = "missing_keyword"
    LOW_SCORE = "low_score"
    PASSED = "passed"


@dataclass
class FilterResult:
    """Result of a filter check on a job."""

    passed: bool
    reason: str
    rule_type: RuleType
    matched_value: str = ""

    def __str__(self) -> str:
        if self.passed:
            return f"PASSED - {self.reason}"
        return f"REJECTED ({self.rule_type.value}) - {self.reason}"


@dataclass
class ScoringWeights:
    """Weights for different scoring factors."""

    title_match: float = 0.4
    skills_match: float = 0.4
    remote_bonus: float = 0.1
    freshness_bonus: float = 0.1


@dataclass
class FilterConfig:
    """Central configuration for job filtering."""

    min_score: float = 0.5
    weights: ScoringWeights = field(default_factory=ScoringWeights)

    required_keywords: list[str] = field(default_factory=list)
    keyword_in_title: bool = False

    title_exclusions: list[str] = field(default_factory=list)
    description_exclusions: list[str] = field(default_factory=list)
    stack_exclusions: list[str] = field(default_factory=list)
    role_exclusions: list[str] = field(default_factory=list)

    blocked_domains: list[str] = field(default_factory=list)
    blocked_url_patterns: list[str] = field(default_factory=list)
    location_exclusions: list[str] = field(default_factory=list)

    positive_signals: list[str] = field(default_factory=list)
    title_keywords: list[str] = field(default_factory=list)

    _config_path: Optional[Path] = field(default=None, repr=False)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "FilterConfig":
        """Load config from YAML file."""
        if path is None:
            path = Path("config/filters.yaml")

        if not path.exists():
            logger.warning(f"Filter config not found at {path}, using defaults")
            return cls()

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        scoring = data.get("scoring", {})
        weights_data = scoring.get("weights", {})
        weights = ScoringWeights(
            title_match=weights_data.get("title_match", 0.4),
            skills_match=weights_data.get("skills_match", 0.4),
            remote_bonus=weights_data.get("remote_bonus", 0.1),
            freshness_bonus=weights_data.get("freshness_bonus", 0.1),
        )

        title_exclusions = _flatten_nested_dict(data.get("title_exclusions", {}))
        stack_exclusions = _flatten_nested_dict(data.get("stack_exclusions", {}))
        role_exclusions = _flatten_nested_dict(data.get("role_exclusions", {}))

        required = data.get("required", {})
        required_keywords_raw = required.get("keywords", [])
        required_keywords = [k.lower() for k in required_keywords_raw if k] if required_keywords_raw else []

        config = cls(
            min_score=scoring.get("min_score", 0.5),
            weights=weights,
            required_keywords=required_keywords,
            keyword_in_title=required.get("keyword_in_title", False),
            title_exclusions=[t.lower() for t in title_exclusions],
            description_exclusions=[d.lower() for d in data.get("description_exclusions", [])],
            stack_exclusions=[s.lower() for s in stack_exclusions],
            role_exclusions=[r.lower() for r in role_exclusions],
            blocked_domains=[d.lower() for d in data.get("blocked_domains", [])],
            blocked_url_patterns=[p.lower() for p in data.get("blocked_url_patterns", [])],
            location_exclusions=[loc.lower() for loc in data.get("location_exclusions", [])],
            positive_signals=[s.lower() for s in data.get("positive_signals", [])],
            title_keywords=[k.lower() for k in data.get("title_keywords", [])],
            _config_path=path,
        )

        logger.info(
            f"Loaded filter config from {path}: "
            f"{len(config.title_exclusions)} title exclusions, "
            f"{len(config.stack_exclusions)} stack exclusions, "
            f"{len(config.role_exclusions)} role exclusions, "
            f"{len(config.blocked_domains)} blocked domains, "
            f"min_score={config.min_score}"
        )

        return config

    def reload(self) -> "FilterConfig":
        """Reload configuration from the original file."""
        if self._config_path is None:
            logger.warning("No config path set, cannot reload")
            return self
        return FilterConfig.load(self._config_path)


def _flatten_nested_dict(data: dict | list) -> list[str]:
    """Flatten a nested dict of lists into a single list."""
    if isinstance(data, list):
        return data

    items: list[str] = []
    for value in data.values():
        if isinstance(value, list):
            items.extend(value)
        elif isinstance(value, dict):
            items.extend(_flatten_nested_dict(value))
    return items
