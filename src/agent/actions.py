"""Action models using element refs."""
from typing import Literal, Union, Optional

from pydantic import BaseModel


PageType = Literal["job_listing", "form", "confirmation", "unknown"]


class FillAction(BaseModel):
    """Fill a text input."""

    action: Literal["fill"] = "fill"
    ref: str
    value: str


class SelectAction(BaseModel):
    """Select an option from dropdown."""

    action: Literal["select"] = "select"
    ref: str
    value: str


class ClickAction(BaseModel):
    """Click a button or element."""

    action: Literal["click"] = "click"
    ref: str


class UploadAction(BaseModel):
    """Upload a file."""

    action: Literal["upload"] = "upload"
    ref: str
    file: str


class WaitAction(BaseModel):
    """Wait for specified time."""

    action: Literal["wait"] = "wait"
    ms: int = 1000


Action = Union[FillAction, SelectAction, ClickAction, UploadAction, WaitAction]


class ActionPlan(BaseModel):
    """Ordered list of actions to execute."""

    page_type: PageType = "unknown"
    reasoning: str
    actions: list[Action]
    needs_more_pages: bool = False
