from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import orjson
import pytest
from typer.testing import CliRunner

from app import cli
from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from app.config import AppSettings


@pytest.fixture
def runner() -> CliRunner:
    """Provide a CLI runner for invoking Typer commands."""
    return CliRunner(mix_stderr=False)


def test_collect_command_invokes_collector(
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
    settings: AppSettings,
) -> None:
    """Collect command should configure the collector with overrides and report output."""
    captured: dict[str, AppSettings] = {}

    async def fake_run() -> dict[str, int]:
        return {"projects": 2, "seen": 5, "written": 4}

    class FakeCollector:
        def __init__(self, init_settings: AppSettings) -> None:
            captured["settings"] = init_settings

        async def run(self) -> dict[str, int]:
            return await fake_run()

    monkeypatch.setattr(cli, "MergeRequestCollector", FakeCollector)
    monkeypatch.setattr(cli, "load_settings", lambda: settings)

    result = runner.invoke(
        cli.app,
        [
            "collect",
            "--since",
            "2024-02-01T00:00:00Z",
            "--group",
            "custom/group",
        ],
    )

    assert result.exit_code == 0
    assert "Collected 4 merge requests" in result.stdout

    used_settings: AppSettings = captured["settings"]
    assert used_settings.report_since == "2024-02-01T00:00:00Z"
    assert used_settings.group_id_or_path == "custom/group"


def test_aggregate_command_uses_cache_dir(
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
    tmp_path: Path,
    settings: AppSettings,
) -> None:
    """Aggregate command should target the configured cache directory and output path."""
    captured: dict[str, Path] = {}

    def fake_load_settings() -> AppSettings:
        return settings.model_copy(update={"cache_dir": tmp_path})

    class FakeAggregationService:
        def __init__(self, *, cache_path: Path, output_path: Path, **_: object) -> None:
            captured["cache_path"] = cache_path
            captured["output_path"] = output_path

        def run(self) -> SimpleNamespace:
            return SimpleNamespace(projects=[1], people=[1])

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli, "AggregationService", FakeAggregationService)

    result = runner.invoke(cli.app, ["aggregate"])

    assert result.exit_code == 0
    assert "Aggregated 1 projects and 1 people" in result.stdout

    cache_path: Path = captured["cache_path"]
    output_path: Path = captured["output_path"]
    assert str(cache_path).endswith("merge_requests.jsonl")
    assert output_path.name == "report.json"


def test_render_command_outputs_manifest(
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    """Render command should echo the number of published artifacts."""
    manifest = {"index.html": "checksum"}

    class FakeRenderService:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def run(self) -> dict[str, str]:
            (tmp_path / "public").mkdir(parents=True, exist_ok=True)
            return manifest

    monkeypatch.setattr(cli, "RenderService", FakeRenderService)

    result = runner.invoke(cli.app, ["render"])

    assert result.exit_code == 0
    assert "Rendered 1 artifacts" in result.stdout


@pytest.mark.parametrize(
    "exc_factory",
    [
        lambda: FileNotFoundError("report.json not found"),
        lambda: orjson.JSONDecodeError("invalid json", "{}", 0),
        lambda: _build_validation_error(),
        lambda: OSError("failed to write to build directory"),
    ],
    ids=["file-not-found", "json-decode", "validation", "os-error"],
)
def test_render_command_handles_expected_errors(
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
    exc_factory: Callable[[], Exception],
) -> None:
    """Render command should surface expected runtime errors to the user."""
    error = exc_factory()
    error_message = str(error)

    class FailingRenderService:
        def __init__(self, **_: object) -> None:
            return

        def run(self) -> dict[str, str]:
            raise error

    monkeypatch.setattr(cli, "RenderService", FailingRenderService)

    result = runner.invoke(cli.app, ["render"])

    assert result.exit_code == 1
    assert "Failed to render dashboards:" in result.stderr
    assert error_message.splitlines()[0] in result.stderr


def _build_validation_error() -> ValidationError:
    class DummyModel(BaseModel):
        value: int

    try:
        DummyModel.model_validate({"value": "invalid"})
    except ValidationError as exc:
        return exc
    raise AssertionError("Expected DummyModel to raise a validation error")


def test_doctor_command_invokes_health_check(
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
    settings: AppSettings,
) -> None:
    """Doctor command should call the asynchronous health check."""
    called: dict[str, object] = {}

    async def fake_doctor(passed_settings: AppSettings) -> None:
        called["settings"] = passed_settings

    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "_doctor", fake_doctor)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert called["settings"] == settings


@pytest.mark.parametrize("command", ["collect", "aggregate", "doctor"])
def test_commands_exit_when_configuration_invalid(
    monkeypatch: pytest.MonkeyPatch,
    runner: CliRunner,
    command: str,
) -> None:
    """Commands should surface configuration errors and exit with code 1."""

    def fake_load_settings() -> AppSettings:
        msg = "GLMR_GITLAB_TOKEN must be configured"
        raise ValueError(msg)

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)

    if command == "collect":
        def fail_collector(*_: object, **__: object) -> None:
            raise AssertionError("collector should not run when configuration is invalid")

        monkeypatch.setattr(cli, "MergeRequestCollector", fail_collector)

    result = runner.invoke(cli.app, [command])

    assert result.exit_code == 1
    assert "Configuration error: GLMR_GITLAB_TOKEN must be configured" in result.stderr
