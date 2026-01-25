"""User profile management."""
import logging
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Experience(BaseModel):
    """Work experience entry."""
    title: str
    company: str
    dates: str
    highlights: list[str] = []


class Education(BaseModel):
    """Education entry."""
    institution: str
    description: str = ""


class ExtraInfo(BaseModel):
    """Additional profile information for job applications."""
    work_authorization: str = "US Citizen"
    requires_sponsorship: bool = False
    willing_to_relocate: bool = False
    remote_only: bool = True
    veteran: bool = False
    clearance: bool = False


class Profile(BaseModel):
    """User profile for job applications."""
    first_name: str
    last_name: str
    email: str
    phone: str
    location: str
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    resume_path: str = ""

    years_experience: int = 0
    current_title: str = ""
    summary: str = ""
    skills: list[str] = []

    experience: list[Experience] = []
    education: list[Education] = []

    extra: ExtraInfo = ExtraInfo()


def load_profile(path: Path) -> Profile:
    """Load profile from YAML file.

    Args:
        path: Path to the profile YAML file.

    Returns:
        Profile instance with loaded data.
    """
    logger.info(f"Loading profile from {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if "extra" in data and isinstance(data["extra"], dict):
        data["extra"] = ExtraInfo(**data["extra"])

    return Profile(**data)
