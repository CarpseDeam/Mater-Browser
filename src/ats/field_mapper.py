"""Maps user profile fields to ATS-specific field names."""
from typing import Any, Optional


# Standard profile field names
PROFILE_FIELDS = [
    "first_name", "last_name", "email", "phone", "location",
    "city", "state", "zip", "country", "linkedin_url", "github_url",
    "portfolio_url", "years_experience", "current_title",
    "work_authorization", "requires_sponsorship", "willing_to_relocate",
]

# ATS-specific field mappings: profile_field -> ats_field_name
WORKDAY_FIELDS: dict[str, str] = {
    "first_name": "firstName",
    "last_name": "lastName",
    "email": "email",
    "phone": "phone",
    "city": "city",
    "state": "state",
    "zip": "postalCode",
    "country": "country",
    "linkedin_url": "linkedInUrl",
}

GREENHOUSE_FIELDS: dict[str, str] = {
    "first_name": "first_name",
    "last_name": "last_name",
    "email": "email",
    "phone": "phone",
    "location": "location",
    "linkedin_url": "linkedin_url",
}

LEVER_FIELDS: dict[str, str] = {
    "first_name": "name",  # Lever uses single name field sometimes
    "email": "email",
    "phone": "phone",
    "linkedin_url": "urls[LinkedIn]",
    "github_url": "urls[GitHub]",
    "portfolio_url": "urls[Portfolio]",
}

ICIMS_FIELDS: dict[str, str] = {
    "first_name": "FirstName",
    "last_name": "LastName",
    "email": "Email",
    "phone": "Phone",
    "city": "City",
    "state": "State",
    "zip": "PostalCode",
    "country": "Country",
}

PHENOM_FIELDS: dict[str, str] = {
    "first_name": "firstName",
    "last_name": "lastName",
    "email": "email",
    "phone": "phoneNumber",
    "city": "city",
    "state": "state",
    "zip": "zipCode",
    "country": "country",
}

INDEED_FIELDS: dict[str, str] = {
    "first_name": "firstName",
    "last_name": "lastName",
    "email": "email",
    "phone": "phone",
    "city": "city",
    "state": "state",
    "zip": "postalCode",
}


class FieldMapper:
    """Maps profile data to ATS-specific field names and values."""

    def __init__(self, profile: dict[str, Any]) -> None:
        self._profile = profile
        self._mappings = {
            "workday": WORKDAY_FIELDS,
            "greenhouse": GREENHOUSE_FIELDS,
            "lever": LEVER_FIELDS,
            "icims": ICIMS_FIELDS,
            "phenom": PHENOM_FIELDS,
            "indeed": INDEED_FIELDS,
        }

    def get_value(self, ats_type: str, profile_field: str) -> Optional[str]:
        """Get profile value for a standard field name."""
        value = self._profile.get(profile_field)
        if value is None and profile_field in ["city", "state", "zip"]:
            value = self._extract_from_location(profile_field)
        return str(value) if value else None

    def get_ats_field_name(
        self, ats_type: str, profile_field: str
    ) -> Optional[str]:
        """Get the ATS-specific field name for a profile field."""
        mapping = self._mappings.get(ats_type, {})
        return mapping.get(profile_field)

    def get_mapped_data(self, ats_type: str) -> dict[str, str]:
        """Get all profile data mapped to ATS field names."""
        mapping = self._mappings.get(ats_type, {})
        result = {}
        for profile_field, ats_field in mapping.items():
            value = self.get_value(ats_type, profile_field)
            if value:
                result[ats_field] = value
        return result

    def _extract_from_location(self, field: str) -> Optional[str]:
        """Extract city/state/zip from location string."""
        location = self._profile.get("location", "")
        if not location:
            return None

        # Try to parse "City, ST ZIP" or "City, State"
        parts = [p.strip() for p in location.split(",")]
        if field == "city" and parts:
            return parts[0]
        if field == "state" and len(parts) > 1:
            state_zip = parts[-1].strip().split()
            return state_zip[0] if state_zip else None
        if field == "zip" and len(parts) > 1:
            state_zip = parts[-1].strip().split()
            return state_zip[1] if len(state_zip) > 1 else None
        return None
