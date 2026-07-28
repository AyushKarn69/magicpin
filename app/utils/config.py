"""Configuration management using Pydantic Settings."""

import json
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8080, description="Server port")
    version: str = Field(default="1.0.0", description="Application version")

    # Team Info
    team_name: str = Field(default="Team Vera", description="Team name")
    team_members: str = Field(
        default='["Engineer1", "Engineer2"]', description="Team members as JSON array"
    )
    contact_email: str = Field(default="team@example.com", description="Contact email")

    # LLM
    openai_api_key: str = Field(default="", description="Groq API key")
    model_name: str = Field(default="llama-3.3-70b-versatile", description="LLM model name")

    # Approach
    approach: str = Field(
        default="Deterministic business reasoning pipeline with LLM-based natural language composition",
        description="Bot approach description",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    def get_team_members_list(self) -> list[str]:
        """Parse team_members JSON string to list."""
        try:
            return json.loads(self.team_members)
        except json.JSONDecodeError:
            return ["Engineer1", "Engineer2"]


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
