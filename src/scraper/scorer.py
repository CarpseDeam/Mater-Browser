"""Job scoring based on profile match."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from .jobspy_client import JobListing

logger = logging.getLogger(__name__)

ACCOUNT_REQUIRED_DOMAINS: list[str] = [
    "workday.com",
    "myworkdayjobs.com",
    "taleo.net",
    "brassring.com",
    "icims.com",
    "lever.co",
    "greenhouse.io",
    "jobvite.com",
    "ultipro.com",
    "successfactors.com",
    "smartrecruiters.com",
    "paylocity.com",
    "adp.com",
    "cornerstoneondemand.com",
    "pwc.com",
    "wd1.myworkdaysite.com",
    "wd3.myworkdaysite.com",
    "wd5.myworkdaysite.com",
]

# Tech stacks to exclude - incompatible with Python backend focus
STACK_EXCLUSIONS: list[str] = [
    # .NET ecosystem
    ".net", "dotnet", "c#", "csharp", "asp.net", "blazor", "f#",
    # Java ecosystem
    "java developer", "java engineer", "spring boot", "spring framework",
    "kotlin", "scala", "jvm",
    # Frontend-only frameworks (as primary requirement)
    "angular", "react developer", "react engineer", "vue developer",
    "vue engineer", "frontend developer", "front-end developer",
    "frontend engineer", "front-end engineer", "ui developer", "ui engineer",
    # Other backend stacks
    "php developer", "php engineer", "laravel", "symfony", "wordpress",
    "ruby developer", "ruby engineer", "rails", "ruby on rails",
    "golang developer", "go developer", "go engineer", "rust developer",
    # Mobile
    "ios developer", "ios engineer", "android developer", "android engineer",
    "swift developer", "mobile developer", "mobile engineer", "react native",
    "flutter", "kotlin developer",
    # Enterprise/Legacy
    "salesforce", "servicenow", "sap ", "oracle developer", "peoplesoft",
    "cobol", "mainframe", "as400",
    # Data Science (different from Data Engineering)
    "machine learning engineer", "ml engineer", "ai engineer",
    "data scientist", "research scientist",
    # Cloud/IoT/Embedded (not Python backend)
    "cloud developer", "cloud dev", "iot developer", "iot engineer",
    "embedded developer", "embedded engineer", "firmware",
    "azure developer", "gcp developer", "aws developer",
    # Java/Rust when primary (in title)
    "java", "rust developer", "rust engineer",
]

# Role types to exclude
ROLE_EXCLUSIONS: list[str] = [
    # Seniority mismatches (4+ years = mid-senior, not junior)
    "junior", "jr.", "jr ", "entry level", "entry-level",
    "associate developer", "associate engineer",
    "intern", "internship", "apprentice", "trainee", "graduate",
    # Non-development roles
    "system admin", "sysadmin", "systems administrator",
    "network admin", "network engineer", "infrastructure engineer",
    "helpdesk", "help desk", "it support", "tech support",
    "desktop support", "support engineer", "support specialist",
    # QA/Testing
    "qa analyst", "qa engineer", "quality assurance", "test engineer",
    "sdet", "automation tester",
    # Management/Leadership
    "engineering manager", "tech lead", "team lead", "director",
    "vp of engineering", "head of engineering", "cto",
    # Security-specific
    "security engineer", "security analyst", "penetration tester",
    "cybersecurity", "infosec",
    # DevOps-only (different from Platform Engineering with coding)
    "devops engineer", "site reliability", "sre",
    "cloud engineer", "cloud architect",
    # Over-senior
    "staff ", "staff,", "principal", "distinguished",
    "senior staff", "lead engineer", "lead developer", "architect",
    # Full Stack (often means frontend-heavy or jack-of-all-trades)
    "full stack", "fullstack", "full-stack",
]

TITLE_HARD_EXCLUSIONS: list[str] = [
    "staff", "principal", "distinguished", "lead", "architect",
    "director", "vp", "head of", "chief",
    "manager", "management",
    "junior", "jr", "entry", "intern", "graduate", "apprentice",
    "ios", "android", "mobile", "frontend", "front-end", "front end",
    "devops", "sre", "site reliability", "cloud engineer", "cloud developer",
    "security", "infosec", "cyber",
    "data scientist", "ml engineer", "machine learning", "ai engineer",
    "qa", "quality assurance", "test engineer", "sdet",
    "support", "helpdesk",
    "salesforce", "servicenow", "sap",
    ".net", "c#", "java developer", "java engineer", "php", "ruby", "golang", "go developer",
    "iot", "embedded", "firmware",
]

# Positive signals that boost score - these indicate good fit
POSITIVE_SIGNALS: list[str] = [
    # Python ecosystem
    "fastapi", "django", "flask", "sqlalchemy", "pydantic",
    "celery", "asyncio", "pytest",
    # Data/Infrastructure
    "postgresql", "postgres", "snowflake", "redshift",
    "airflow", "dagster", "prefect", "dbt",
    "kafka", "rabbitmq", "redis",
    # Cloud/DevOps (as tools, not primary role)
    "aws", "docker", "kubernetes", "terraform",
    "ci/cd", "github actions",
    # Architecture
    "microservices", "rest api", "graphql",
    "distributed systems", "event-driven",
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
        role_exclusions: Optional[list[str]] = None,
        positive_signals: Optional[list[str]] = None,
        min_score: float = 0.5,
    ) -> None:
        self.profile = profile
        self.skills = [s.lower() for s in profile.get("skills", [])]

        self.title_keywords = [
            k.lower()
            for k in (
                title_keywords
                or [
                    # Primary targets
                    "python", "backend", "back-end", "back end",
                    "platform", "data engineer", "data infrastructure",
                    "systems engineer", "api engineer", "api developer",
                    # Secondary targets (good if combined with Python)
                    "software engineer",
                    "integration", "etl", "pipeline",
                ]
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
                    # Seniority requirements we can't meet
                    "10+ years", "15+ years", "12+ years",
                    "10 years", "15 years", "12 years",
                    # Clearance/Location restrictions
                    "clearance required", "security clearance", "ts/sci",
                    "on-site only", "onsite only", "no remote",
                    "must be local", "relocation required",
                    # Specific tech requirements we don't have
                    "node.js required", "java required", "c++ required",
                    "react required", "angular required",
                ]
            )
        ]
        self.stack_exclusions = [
            k.lower() for k in (stack_exclusions or STACK_EXCLUSIONS)
        ]
        self.role_exclusions = [
            k.lower() for k in (role_exclusions or ROLE_EXCLUSIONS)
        ]
        self.positive_signals = [
            k.lower() for k in (positive_signals or POSITIVE_SIGNALS)
        ]
        self.min_score = min_score

    def _requires_external_account(self, job: JobListing) -> tuple[bool, str]:
        """Check if job URL points to ATS requiring account creation."""
        url_lower = job.url.lower() if job.url else ""
        for domain in ACCOUNT_REQUIRED_DOMAINS:
            if domain in url_lower:
                return True, domain
        return False, ""

    def _check_exclusion(self, job: JobListing) -> Optional[str]:
        """Check if job should be excluded and return the reason, or None if it passes."""
        title_lower = job.title.lower()

        for excl in TITLE_HARD_EXCLUSIONS:
            if excl in title_lower:
                return f"title contains excluded term '{excl}'"

        requires_account, domain = self._requires_external_account(job)
        if requires_account:
            return f"external ATS requires account: {domain}"

        desc_lower = job.description.lower()
        combined = f"{title_lower} {desc_lower}"

        for excluded in self.excluded_keywords:
            if excluded in combined:
                return f"matched excluded keyword '{excluded}'"

        for stack in self.stack_exclusions:
            if stack in title_lower:
                return f"incompatible stack '{stack}' in title"

        for role in self.role_exclusions:
            if role in title_lower:
                return f"excluded role '{role}' in title"

        if self.required_keywords:
            if not any(kw in combined for kw in self.required_keywords):
                return f"missing required keywords {self.required_keywords}"

        if "python" not in title_lower and "python" not in desc_lower[:500]:
            return "python not in title or early description"

        return None

    def passes_filter(self, job: JobListing) -> bool:
        """Check if a single job passes all exclusion checks and meets min_score."""
        if self._check_exclusion(job) is not None:
            return False
        return self.score(job) >= self.min_score

    def get_exclusion_reason(self, job: JobListing) -> str:
        """Return the reason a job was excluded, or 'below min_score' if score too low."""
        reason = self._check_exclusion(job)
        if reason:
            return reason
        score = self.score(job)
        if score < self.min_score:
            return f"score {score:.2f} below min_score {self.min_score}"
        return "passed all checks"

    def score(self, job: JobListing) -> float:
        """
        Score a job from 0.0 to 1.0.

        Factors:
        - Title keyword match (40%)
        - Skills + positive signals match in description (40%)
        - Remote preference (10%)
        - Freshness (10%)

        Exclusions:
        - Excluded keywords in title/description
        - Incompatible tech stacks in title
        - Excluded role types in title
        - Missing required keywords
        """
        requires_account, domain = self._requires_external_account(job)
        if requires_account:
            logger.info(f"Skipping {job.title} - external ATS requires account: {domain}")
            return 0.0

        exclusion_reason = self._check_exclusion(job)
        if exclusion_reason:
            logger.debug(f"Excluded '{job.title}' - {exclusion_reason}")
            return 0.0

        title_lower = job.title.lower()
        desc_lower = job.description.lower()

        score = 0.0

        title_matches = sum(1 for kw in self.title_keywords if kw in title_lower)
        if self.title_keywords:
            score += 0.4 * min(title_matches / 2, 1.0)

        # Skills/tech match in description (40%)
        # Count matches from both profile skills AND positive signals
        skill_matches = sum(1 for skill in self.skills if skill in desc_lower)
        signal_matches = sum(1 for signal in self.positive_signals if signal in desc_lower)
        combined_matches = skill_matches + signal_matches

        if self.skills or self.positive_signals:
            # Need at least 3 matches for full score
            score += 0.4 * min(combined_matches / 3, 1.0)

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
