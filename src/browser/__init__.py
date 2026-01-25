"""Browser automation: CDP connection, page wrapper, and tab management."""
from .connection import BrowserConnection
from .page import Page
from .tabs import TabManager

__all__ = ["BrowserConnection", "Page", "TabManager"]
