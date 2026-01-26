"""Application agent models, enums, and constants."""
from dataclasses import dataclass
from enum import Enum


# Timeouts
APPLICATION_TIMEOUT_SECONDS: float = 300.0
EXTERNAL_REDIRECT_TIMEOUT_MS: int = 30000
PAGE_LOAD_TIMEOUT_MS: int = 30000
ELEMENT_TIMEOUT_MS: int = 10000
CLICK_TIMEOUT_MS: int = 8000
SHORT_WAIT_MS: int = 500
MEDIUM_WAIT_MS: int = 1500
LONG_WAIT_MS: int = 2500

# Retry counts
MAX_NAVIGATION_RETRIES: int = 3
MAX_CLICK_RETRIES: int = 3
MAX_POPUP_WAIT_ATTEMPTS: int = 5

# Loop detection
LOOP_DETECTION_THRESHOLD: int = 3
LOOP_ELEMENT_COUNT_TOLERANCE: int = 5


class JobSource(Enum):
    """Source platform for job listing."""
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    DICE = "dice"
    DIRECT = "direct"


LINKEDIN_PATTERNS: list[str] = ["linkedin.com/jobs", "linkedin.com/job"]
INDEED_PATTERNS: list[str] = ["indeed.com/viewjob", "indeed.com/jobs", "indeed.com/rc"]


LOGIN_URL_PATTERNS: dict[str, list[str]] = {
    "linkedin": [
        "linkedin.com/login",
        "linkedin.com/checkpoint",
        "linkedin.com/uas/login",
    ],
    "indeed": [
        "secure.indeed.com/auth",
        "indeed.com/account/login",
        "indeed.com/account/signin",
    ],
    "generic": [
        "/login",
        "/signin",
        "/sign-in",
        "/auth",
        "/authenticate",
    ],
}


class ApplicationStatus(Enum):
    """Status of job application attempt."""
    SUCCESS = "success"
    FAILED = "failed"
    NO_APPLY_BUTTON = "no_apply_button"
    MAX_PAGES_REACHED = "max_pages_reached"
    STUCK = "stuck"
    ERROR = "error"
    NEEDS_LOGIN = "needs_login"


@dataclass
class ApplicationResult:
    """Result of a job application attempt."""
    status: ApplicationStatus
    message: str
    pages_processed: int = 0
    url: str = ""


ACCOUNT_CREATION_URL_PATTERNS: list[str] = [
    "/login", "/signin", "/sign-in", "/signup", "/sign-up",
    "/register", "/create-account", "/authenticate",
    "icims.com", "myworkdayjobs.com", "taleo.net",
]

ACCOUNT_CREATION_CONTENT: list[str] = [
    "sign in", "log in", "create an account", "register now",
    "confirm password", "already have an account", "forgot password",
]
