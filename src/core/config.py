"""Application configuration using pydantic-settings."""
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class BrowserConfig(BaseModel):
    """Browser connection configuration."""

    cdp_port: int = 9333
    connect_retries: int = 5
    retry_delay: float = 2.0
    timeout: int = 30000


class ClaudeConfig(BaseModel):
    """Claude API configuration."""

    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096


class Settings(BaseSettings):
    """Application settings loaded from YAML or environment."""

    browser: BrowserConfig = BrowserConfig()
    claude: ClaudeConfig = ClaudeConfig()

    @classmethod
    def from_yaml(cls, path: Path) -> "Settings":
        """Load settings from a YAML file.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            Settings instance with loaded configuration.
        """
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)
