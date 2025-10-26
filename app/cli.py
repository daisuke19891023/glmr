"""Command-line entry point for the GLMR tool."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

import typer

from app.collector import MergeRequestCollector
from app.config import AppSettings, load_settings
from app.gitlab_client import GitLabClient

app = typer.Typer(add_completion=False, help="GitLab Merge Request metrics tooling.")


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable verbose logging output.")] = False,
) -> None:
    """Configure logging before executing a sub-command."""
    _configure_logging(verbose)


@app.command()
def collect(
    since: Annotated[
        str | None,
        typer.Option(
            "--since",
            help="Override the configured updated_after timestamp.",
        ),
    ] = None,
    group: Annotated[
        str | None,
        typer.Option(
            "--group",
            help="Override the configured group path or ID.",
        ),
    ] = None,
) -> None:
    """Collect merge request data and update the local JSONL cache."""
    settings = _patched_settings(since=since, group=group)
    collector = MergeRequestCollector(settings)
    summary = asyncio.run(collector.run())
    typer.echo(
        "Collected {written} merge requests across {projects} projects (considered {seen}).".format(**summary),
    )


@app.command()
def aggregate() -> None:  # pragma: no cover - placeholder for future implementation
    """Aggregate raw data into reporting metrics."""
    typer.echo("Aggregation pipeline not yet implemented in this milestone.")


@app.command()
def render() -> None:  # pragma: no cover - placeholder for future implementation
    """Render HTML dashboards from aggregated metrics."""
    typer.echo("Rendering pipeline not yet implemented in this milestone.")


@app.command()
def doctor() -> None:
    """Validate configuration and verify GitLab API connectivity."""
    settings = load_settings()
    typer.echo(f"Loaded configuration for group: {settings.group_id_or_path}")
    asyncio.run(_doctor(settings))


async def _doctor(settings: AppSettings) -> None:
    try:
        async with GitLabClient(settings) as client:
            response = await client.request("GET", "/user")
            payload = response.json()
    except Exception as exc:  # pragma: no cover - direct user feedback
        typer.echo(f"Failed to reach GitLab API: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"Authenticated as: {payload.get('username', 'unknown')}")


def _patched_settings(*, since: str | None, group: str | None) -> AppSettings:
    settings = load_settings()
    updates: dict[str, object] = {}
    if since:
        updates["report_since"] = since
    if group:
        updates["group_id_or_path"] = group
    if updates:
        settings = settings.model_copy(update=updates)
    return settings


if __name__ == "__main__":
    app()
