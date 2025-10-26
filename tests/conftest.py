"""Shared pytest fixtures for the GLMR test suite."""

from __future__ import annotations

import pytest

from app.config import AppSettings

pytest_plugins = ("respx",)


@pytest.fixture
def settings() -> AppSettings:
    """Provide application settings with deterministic defaults for tests."""
    return AppSettings.model_validate(
        {
            "gitlab_api_base": "https://gitlab.example.com/api/v4",
            "gitlab_token": "token",  # pragma: allowlist secret
            "group_id_or_path": "example/group",
            "report_since": "2024-01-01T00:00:00Z",
        },
    )
