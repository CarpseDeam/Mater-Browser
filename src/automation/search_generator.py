"""Search term generator for autonomous job searching."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from src.profile.manager import Profile

logger = logging.getLogger(__name__)

TITLE_VARIATIONS: list[str] = ["Engineer", "Developer", "Specialist"]
MAX_SKILLS_FOR_SEARCH: int = 5
DEFAULT_LOCATION: str = "remote"


@dataclass
class SearchGenerator:
    """Generates search term variations from user profile.

    Builds search queries by combining:
    - Title variations from current_title
    - Top skills from profile
    - Standard job title suffixes

    Attributes:
        profile: User profile containing title and skills.
        location: Location to append to searches.
    """

    profile: Profile
    location: str = DEFAULT_LOCATION
    _terms: list[str] = field(default_factory=list, init=False)
    _index: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        """Generate search terms after initialization."""
        self._terms = self._build_terms()
        logger.info(f"Generated {len(self._terms)} search terms")

    def _extract_title_parts(self) -> list[str]:
        """Extract meaningful parts from current_title.

        Handles titles like "Backend/Platform Engineer" -> ["Backend", "Platform"]
        """
        title = self.profile.current_title
        if not title:
            return []

        cleaned = re.sub(r"\s+(Engineer|Developer|Specialist)\b", "", title, flags=re.I)
        parts = re.split(r"[/,&]+", cleaned)
        return [p.strip() for p in parts if p.strip()]

    def _build_terms(self) -> list[str]:
        """Build all search term combinations."""
        terms: list[str] = []
        title_parts = self._extract_title_parts()
        skills = self.profile.skills[:MAX_SKILLS_FOR_SEARCH]

        for part in title_parts:
            for variation in TITLE_VARIATIONS:
                term = f"{part} {variation} {self.location}"
                if term not in terms:
                    terms.append(term)

        for skill in skills:
            for variation in TITLE_VARIATIONS:
                term = f"{skill} {variation} {self.location}"
                if term not in terms:
                    terms.append(term)

        if self.profile.current_title:
            full_title = f"{self.profile.current_title} {self.location}"
            if full_title not in terms:
                terms.insert(0, full_title)

        if not terms:
            terms.append(f"Software Engineer {self.location}")
            logger.warning("No profile data for search terms, using default")

        return terms

    def generate(self) -> list[str]:
        """Return all generated search terms.

        Returns:
            List of all search query strings.
        """
        return self._terms.copy()

    def next(self) -> str:
        """Return next search term in rotation.

        Returns:
            Next search term, cycling back to start when exhausted.
        """
        if not self._terms:
            return f"Software Engineer {self.location}"

        term = self._terms[self._index]
        self._index = (self._index + 1) % len(self._terms)
        return term

    def reset(self) -> None:
        """Reset rotation index to beginning."""
        self._index = 0

    def __len__(self) -> int:
        """Return number of search terms."""
        return len(self._terms)
