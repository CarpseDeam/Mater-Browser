"""Job scoring based on profile match."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from .jobspy_client import JobListing

logger = logging.getLogger(__name__)

# Tech stacks to exclude for Python-focused searches
STACK_EXCLUSIONS: list[str] = [
    # .NET ecosystem
    ".net", "dotnet", "c#", "csharp", "asp.net", "blazor",
    # Frontend-only (when not full-stack with Python)
    "angular developer", "react developer", "vue developer", "frontend developer", "front-end developer",
    # Java ecosystem
    "java developer", "java engineer", "spring boot", "kotlin",
    # Other backend stacks
    "php", "laravel", "symfony",
    "ruby", "rails", "ruby on rails",
    "golang developer", "go developer",
    # Mobile
    "ios developer", "android developer", "swift developer", "mobile developer",
    # Specific non-Python roles
    "salesforce", "servicenow", "sap ",
]


class JobScorer:
    """Scores jobs based on profile relevance."""

    def __init__(
        self,
        profile: dict,
        title_keywords: Optional[list[str]] = None,
        required_keywords: Optional[list[str]] = None,
        excluded_keywords: Optional[list[str]] = None,
        stack_exclusions: Optional[list[str]] = None,
        min_score: float = 0.4,
    ) -> None:
        self.profile = profile
        self.skills = [s.lower() for s in profile.get("skills", [])]

        self.title_keywords = [
            k.lower()
            for k in (
                title_keywords
                or ["python", "backend", "platform", "systems", "data", "engineer"]
            )
        ]
        self.required_keywords = [
            k.lower() for k in (required_keywords or ["python"])
        ]
        self.excluded_keywords = [
            k.lower()
            for k in (
                excluded_keywords
                or [
                    "senior staff",
                    "principal",
                    "director",
                    "vp",
                    "head of",
                    "10+ years",
                    "15+ years",
                    "clearance required",
                    "on-site only",
                ]
            )
        ]
        self.stack_exclusions = [
            k.lower() for k in (stack_exclusions or STACK_EXCLUSIONS)
        ]
        self.min_score = min_score

    def score(self, job: JobListing) -> float:
        """
        Score a job from 0.0 to 1.0.

        Factors:
        - Title keyword match (40%)
        - Skills match in description (40%)
        - Remote preference (10%)
        - Freshness (10%)

        Exclusions:
        - Excluded keywords in title/description
        - Incompatible tech stacks in title
        - Missing required keywords
        """
        title_lower = job.title.lower()
        desc_lower = job.description.lower()
        combined = f"{title_lower} {desc_lower}"

        for excluded in self.excluded_keywords:
            if excluded in combined:
                logger.debug(f"Excluded '{job.title}' - matched excluded keyword '{excluded}'")
                return 0.0

        for stack in self.stack_exclusions:
            if stack in title_lower:
                logger.debug(f"Excluded '{job.title}' - incompatible stack '{stack}' in title")
                return 0.0

        if self.required_keywords:
            if not any(kw in combined for kw in self.required_keywords):
                logger.debug(f"Excluded '{job.title}' - missing required keywords {self.required_keywords}")
                return 0.0

        score = 0.0

        title_matches = sum(1 for kw in self.title_keywords if kw in title_lower)
        if self.title_keywords:
            score += 0.4 * min(title_matches / 2, 1.0)

        skill_matches = sum(1 for skill in self.skills if skill in desc_lower)
        if self.skills:
            score += 0.4 * min(skill_matches / 5, 1.0)

        if job.is_remote:
            score += 0.1

        if job.date_posted:
            # Handle both date and datetime objects from JobSpy
            posted = job.date_posted
            if hasattr(posted, 'hour'):
                age = datetime.now() - posted
            else:
                age = datetime.now() - datetime.combine(posted, datetime.min.time())
            if age < timedelta(hours=24):
                score += 0.1
            elif age < timedelta(hours=48):
                score += 0.05

        return min(score, 1.0)

    def filter_and_score(self, jobs: list[JobListing]) -> list[JobListing]:
        """Score all jobs and filter by minimum score."""
        scored = []
        excluded_count = 0

        for job in jobs:
            job.score = self.score(job)
            if job.score >= self.min_score:
                scored.append(job)
            elif job.score == 0.0:
                excluded_count += 1

        scored.sort(key=lambda j: j.score, reverse=True)

        logger.info(
            f"Scored {len(jobs)} jobs: {len(scored)} passed (>={self.min_score}), "
            f"{excluded_count} excluded (stack/keyword mismatch)"
        )
        return scored
