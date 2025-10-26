"""Configuration management for the GLMR application."""

from pathlib import Path
from typing import Literal, cast

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_prefix="GLMR_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    gitlab_api_base: AnyHttpUrl = Field(
        default=cast("AnyHttpUrl", "https://gitlab.com/api/v4"),
        description="Base URL for the GitLab REST API.",
    )
    gitlab_token: SecretStr = Field(
        default=SecretStr(""),
        description="Personal access token used to authenticate GitLab API calls.",
    )
    group_id_or_path: str = Field(
        default="",
        description="The GitLab group ID or full path used as the collection root.",
    )
    report_since: str = Field(
        default="1970-01-01T00:00:00Z",
        description="ISO8601 timestamp used for incremental merge request collection.",
    )
    max_concurrency: int = Field(
        default=5,
        ge=1,
        le=32,
        description="Maximum number of concurrent API calls performed during collection.",
    )
    per_page: int = Field(
        default=100,
        ge=20,
        le=100,
        description="Number of items to request per GitLab API page.",
    )
    comment_dedup_mode: Literal["author", "body"] = Field(
        default="author",
        description="Default deduplication strategy for comment metrics.",
    )
    lang_patterns_file: Path | None = Field(
        default=None,
        description="Path to the YAML file containing locale-specific review patterns.",
    )
    cache_dir: Path = Field(
        default=Path("data/raw/mr"),
        description="Directory used to persist raw merge request JSONL cache entries.",
    )

    @model_validator(mode="after")
    def _enforce_required_fields(self) -> "AppSettings":
        if not self.gitlab_token.get_secret_value():
            msg = "GLMR_GITLAB_TOKEN must be configured"
            raise ValueError(msg)
        if not self.group_id_or_path:
            msg = "GLMR_GROUP_ID_OR_PATH must be configured"
            raise ValueError(msg)
        return self


def load_settings() -> AppSettings:
    """Load application settings from supported sources."""
    return AppSettings()
