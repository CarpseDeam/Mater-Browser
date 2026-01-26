"""Job scoring based on profile match and centralized filter configuration."""
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .filter_config import FilterConfig, FilterResult, RuleType
from .jobspy_client import JobListing

logger = logging.getLogger(__name__)


@dataclass
class FilterStats:
    """Statistics from filtering a batch of jobs."""

    total: int = 0
    passed: int = 0
    rejected: int = 0
    rejection_counts: Counter = field(default_factory=Counter)

    def record_result(self, result: FilterResult) -> None:
        """Record a filter result."""
        self.total += 1
        if result.passed:
            self.passed += 1
        else:
            self.rejected += 1
            self.rejection_counts[result.rule_type.value] += 1

    def log_summary(self) -> None:
        """Log a summary of filtering results."""
        logger.info(f"Filter results: {self.total} jobs -> {self.passed} passed, {self.rejected} rejected")
        if self.rejection_counts:
            breakdown = ", ".join(
                f"{count} {rule_type}" for rule_type, count in self.rejection_counts.most_common()
            )
            logger.info(f"Rejection breakdown: {breakdown}")


class JobScorer:
    """Scores jobs based on profile relevance using centralized configuration."""

    def __init__(
        self,
        profile: dict,
        config: Optional[FilterConfig] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        self.profile = profile
        self.skills = [s.lower() for s in profile.get("skills", [])]

        if config is not None:
            self._config = config
        else:
            self._config = FilterConfig.load(config_path)

        self._last_filter_stats: Optional[FilterStats] = None

    @property
    def config(self) -> FilterConfig:
        """Return the current filter configuration."""
        return self._config

    @property
    def min_score(self) -> float:
        """Return minimum score threshold."""
        return self._config.min_score

    @property
    def last_filter_stats(self) -> Optional[FilterStats]:
        """Return stats from the last filter_and_score call."""
        return self._last_filter_stats

    def reload_config(self) -> None:
        """Reload filter configuration from file."""
        self._config = self._config.reload()

    def check_filter(self, job: JobListing) -> FilterResult:
        """Check if job passes all filters and return detailed result."""
        title_lower = job.title.lower()
        url_lower = job.url.lower() if job.url else ""
        desc_lower = job.description.lower() if job.description else ""
        combined = f"{title_lower} {desc_lower}"

        for excl in self._config.title_exclusions:
            if excl in title_lower:
                return FilterResult(
                    passed=False,
                    reason=f"title contains excluded term: '{excl}'",
                    rule_type=RuleType.TITLE_EXCLUSION,
                    matched_value=excl,
                )

        for domain in self._config.blocked_domains:
            if domain in url_lower:
                return FilterResult(
                    passed=False,
                    reason=f"blocked domain: {domain}",
                    rule_type=RuleType.BLOCKED_DOMAIN,
                    matched_value=domain,
                )

        for pattern in self._config.blocked_url_patterns:
            if pattern in url_lower:
                return FilterResult(
                    passed=False,
                    reason=f"blocked URL pattern: {pattern}",
                    rule_type=RuleType.BLOCKED_URL_PATTERN,
                    matched_value=pattern,
                )

        for excl in self._config.description_exclusions:
            if excl in combined:
                return FilterResult(
                    passed=False,
                    reason=f"matched excluded keyword: '{excl}'",
                    rule_type=RuleType.DESCRIPTION_EXCLUSION,
                    matched_value=excl,
                )

        for stack in self._config.stack_exclusions:
            if stack in title_lower:
                return FilterResult(
                    passed=False,
                    reason=f"incompatible stack in title: '{stack}'",
                    rule_type=RuleType.STACK_EXCLUSION,
                    matched_value=stack,
                )

        for role in self._config.role_exclusions:
            if role in title_lower:
                return FilterResult(
                    passed=False,
                    reason=f"excluded role in title: '{role}'",
                    rule_type=RuleType.ROLE_EXCLUSION,
                    matched_value=role,
                )

        if self._config.required_keywords:
            search_text = title_lower if self._config.keyword_in_title else combined
            if not any(kw in search_text for kw in self._config.required_keywords):
                return FilterResult(
                    passed=False,
                    reason=f"missing required keyword: {self._config.required_keywords}",
                    rule_type=RuleType.MISSING_KEYWORD,
                    matched_value=str(self._config.required_keywords),
                )

        score = self._calculate_score(job, title_lower, desc_lower)
        if score < self._config.min_score:
            return FilterResult(
                passed=False,
                reason=f"score {score:.2f} below minimum {self._config.min_score}",
                rule_type=RuleType.LOW_SCORE,
                matched_value=f"{score:.2f}",
            )

        return FilterResult(
            passed=True,
            reason=f"score: {score:.2f}",
            rule_type=RuleType.PASSED,
            matched_value=f"{score:.2f}",
        )

    def _calculate_score(
        self, job: JobListing, title_lower: str, desc_lower: str
    ) -> float:
        """Calculate the score for a job (0.0 to 1.0)."""
        weights = self._config.weights
        score = 0.0

        title_matches = sum(1 for kw in self._config.title_keywords if kw in title_lower)
        if self._config.title_keywords:
            score += weights.title_match * min(title_matches / 2, 1.0)

        skill_matches = sum(1 for skill in self.skills if skill in desc_lower)
        signal_matches = sum(
            1 for signal in self._config.positive_signals if signal in desc_lower
        )
        combined_matches = skill_matches + signal_matches

        if self.skills or self._config.positive_signals:
            score += weights.skills_match * min(combined_matches / 3, 1.0)

        if job.is_remote:
            score += weights.remote_bonus

        if job.date_posted:
            posted = job.date_posted
            if hasattr(posted, "hour"):
                age = datetime.now() - posted
            else:
                age = datetime.now() - datetime.combine(posted, datetime.min.time())
            if age < timedelta(hours=24):
                score += weights.freshness_bonus
            elif age < timedelta(hours=48):
                score += weights.freshness_bonus * 0.5

        return min(score, 1.0)

    def score(self, job: JobListing) -> float:
        """Score a job from 0.0 to 1.0. Returns 0.0 if job is excluded."""
        result = self.check_filter(job)

        if not result.passed:
            logger.debug(f'REJECTED "{job.title}" - {result.reason}')
            return 0.0

        title_lower = job.title.lower()
        desc_lower = job.description.lower() if job.description else ""
        final_score = self._calculate_score(job, title_lower, desc_lower)

        logger.debug(f'PASSED "{job.title}" - score: {final_score:.2f}')
        return final_score

    def passes_filter(self, job: JobListing) -> bool:
        """Check if a job passes all filters."""
        result = self.check_filter(job)
        return result.passed

    def get_exclusion_reason(self, job: JobListing) -> str:
        """Return the reason a job was excluded, or 'passed' if it passes."""
        result = self.check_filter(job)
        return result.reason

    def explain(self, job: JobListing) -> str:
        """Return detailed explanation of why job passed or failed."""
        result = self.check_filter(job)

        title_lower = job.title.lower()
        desc_lower = job.description.lower() if job.description else ""
        url_lower = job.url.lower() if job.url else ""

        lines = [
            f"Job: {job.title} at {job.company}",
            f"URL: {job.url}",
            "",
            f"Result: {'PASSED' if result.passed else 'REJECTED'}",
            f"Reason: {result.reason}",
            f"Rule Type: {result.rule_type.value}",
        ]

        if result.matched_value:
            lines.append(f"Matched Value: {result.matched_value}")

        lines.append("")
        lines.append("--- Filter Checks ---")

        title_hits = [e for e in self._config.title_exclusions if e in title_lower]
        lines.append(f"Title exclusions matched: {title_hits if title_hits else 'none'}")

        domain_hits = [d for d in self._config.blocked_domains if d in url_lower]
        lines.append(f"Blocked domains matched: {domain_hits if domain_hits else 'none'}")

        combined = f"{title_lower} {desc_lower}"
        desc_hits = [e for e in self._config.description_exclusions if e in combined]
        lines.append(f"Description exclusions matched: {desc_hits if desc_hits else 'none'}")

        stack_hits = [s for s in self._config.stack_exclusions if s in title_lower]
        lines.append(f"Stack exclusions matched: {stack_hits if stack_hits else 'none'}")

        role_hits = [r for r in self._config.role_exclusions if r in title_lower]
        lines.append(f"Role exclusions matched: {role_hits if role_hits else 'none'}")

        search_text = title_lower if self._config.keyword_in_title else combined
        kw_found = [kw for kw in self._config.required_keywords if kw in search_text]
        lines.append(f"Required keywords found: {kw_found if kw_found else 'none'}")

        lines.append("")
        lines.append("--- Scoring ---")
        score = self._calculate_score(job, title_lower, desc_lower)
        lines.append(f"Final score: {score:.2f} (min: {self._config.min_score})")

        title_matches = [kw for kw in self._config.title_keywords if kw in title_lower]
        lines.append(f"Title keywords matched: {title_matches}")

        skill_matches = [s for s in self.skills if s in desc_lower]
        signal_matches = [s for s in self._config.positive_signals if s in desc_lower]
        lines.append(f"Skills matched: {skill_matches}")
        lines.append(f"Positive signals matched: {signal_matches}")
        lines.append(f"Remote: {job.is_remote}")
        lines.append(f"Date posted: {job.date_posted}")

        return "\n".join(lines)

    def filter_and_score(self, jobs: list[JobListing]) -> list[JobListing]:
        """Score all jobs and filter by minimum score. Logs detailed stats."""
        stats = FilterStats()
        scored: list[JobListing] = []

        for job in jobs:
            result = self.check_filter(job)
            stats.record_result(result)

            if result.passed:
                job.score = self._calculate_score(
                    job,
                    job.title.lower(),
                    job.description.lower() if job.description else "",
                )
                scored.append(job)
                logger.debug(f'PASSED "{job.title} at {job.company}" - score: {job.score:.2f}')
            else:
                job.score = 0.0
                logger.debug(f'REJECTED "{job.title} at {job.company}" - {result.reason}')

        scored.sort(key=lambda j: j.score, reverse=True)
        self._last_filter_stats = stats
        stats.log_summary()

        return scored
