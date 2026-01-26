"""Maps profile fields to ATS-specific field names."""
from typing import Any


class FieldMapper:
    """Maps generic profile fields to ATS-specific field names."""

    FIELD_MAPPINGS: dict[str, dict[str, list[str]]] = {
        "first_name": {
            "workday": ["firstName", "legalNameSection_firstName"],
            "greenhouse": ["first_name", "firstName"],
            "lever": ["name", "first_name"],
            "icims": ["firstName", "Contact_Information_firstname"],
            "phenom": ["firstName", "first-name"],
            "default": ["first_name", "firstName", "fname", "first"],
        },
        "last_name": {
            "workday": ["lastName", "legalNameSection_lastName"],
            "greenhouse": ["last_name", "lastName"],
            "lever": ["name", "last_name"],
            "icims": ["lastName", "Contact_Information_lastname"],
            "phenom": ["lastName", "last-name"],
            "default": ["last_name", "lastName", "lname", "last"],
        },
        "email": {
            "workday": ["email", "emailAddress"],
            "greenhouse": ["email"],
            "lever": ["email"],
            "icims": ["email", "Contact_Information_email"],
            "phenom": ["email", "emailAddress"],
            "default": ["email", "emailAddress", "e-mail"],
        },
        "phone": {
            "workday": ["phone", "phoneNumber", "mobilePhone"],
            "greenhouse": ["phone"],
            "lever": ["phone"],
            "icims": ["phone", "Contact_Information_phone"],
            "phenom": ["phone", "phoneNumber"],
            "default": ["phone", "phoneNumber", "telephone", "mobile"],
        },
        "city": {
            "workday": ["city", "addressSection_city"],
            "greenhouse": ["city"],
            "icims": ["city", "Contact_Information_city"],
            "phenom": ["city"],
            "default": ["city"],
        },
        "state": {
            "workday": ["state", "addressSection_state", "region"],
            "greenhouse": ["state"],
            "icims": ["state"],
            "phenom": ["state", "region"],
            "default": ["state", "region", "province"],
        },
        "zip": {
            "workday": ["postalCode", "addressSection_postalCode"],
            "greenhouse": ["zip", "postal_code"],
            "icims": ["postalCode", "zip"],
            "phenom": ["postalCode", "zipCode"],
            "default": ["zip", "zipCode", "postalCode", "postal"],
        },
        "country": {
            "workday": ["country", "addressSection_country"],
            "greenhouse": ["country"],
            "icims": ["country"],
            "phenom": ["country"],
            "default": ["country"],
        },
        "linkedin_url": {
            "workday": ["linkedIn", "linkedInUrl"],
            "greenhouse": ["linkedin_url", "linkedin"],
            "lever": ["urls[LinkedIn]", "linkedin"],
            "icims": ["linkedIn"],
            "phenom": ["linkedIn", "linkedin"],
            "default": ["linkedin", "linkedIn", "linkedin_url"],
        },
        "resume": {
            "workday": ["resume", "uploadedResume"],
            "greenhouse": ["resume", "resume_file"],
            "lever": ["resume"],
            "icims": ["resume", "resumeUpload"],
            "phenom": ["resume", "resumeFile"],
            "default": ["resume", "cv", "resumeUpload"],
        },
    }

    def __init__(self, ats_type: str) -> None:
        self._ats_type = ats_type.lower()

    def get_field_names(self, generic_name: str) -> list[str]:
        """Get ATS-specific field names for a generic field."""
        mapping = self.FIELD_MAPPINGS.get(generic_name, {})
        return mapping.get(self._ats_type, mapping.get("default", [generic_name]))

    def map_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        """Map entire profile to ATS-specific field names."""
        mapped: dict[str, Any] = {}
        for key, value in profile.items():
            field_names = self.get_field_names(key)
            for name in field_names:
                mapped[name] = value
        return mapped
