"""Data models for extracted page elements."""
from typing import Optional

from pydantic import BaseModel


class FormElement(BaseModel):
    """A single form element extracted from the page."""

    selector: str
    tag: str
    type: Optional[str] = None
    name: Optional[str] = None
    id: Optional[str] = None
    label: Optional[str] = None
    placeholder: Optional[str] = None
    value: Optional[str] = None
    options: Optional[list[str]] = None
    required: bool = False
    visible: bool = True


class FormData(BaseModel):
    """Collection of form elements from a page."""

    url: str
    title: str
    elements: list[FormElement]
