"""Command-line entry point for the GLMR tool."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from app.aggregate.service import AggregationService
from app.collector import MergeRequestCollector
from app.config import AppSettings, load_settings
from app.gitlab_client import GitLabClient
from app.render.service import RenderService

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
    try:
        base_settings = load_settings()
        settings = _patched_settings(base_settings, since=since, group=group)
        collector = MergeRequestCollector(settings)
        summary = asyncio.run(collector.run())
    except ValueError as exc:
        _handle_settings_error(exc)
    typer.echo(
        "Collected {written} merge requests across {projects} projects (considered {seen}).".format(**summary),
    )


@app.command()
def aggregate() -> None:
    """Aggregate raw data into reporting metrics."""
    try:
        settings = load_settings()
    except ValueError as exc:
        _handle_settings_error(exc)
    cache_path = settings.cache_dir / "merge_requests.jsonl"
    output_path = Path("data/agg/report.json")
    service = AggregationService(cache_path=cache_path, output_path=output_path)
    report = service.run()
    typer.echo(
        f"Aggregated {len(report.projects)} projects and {len(report.people)} people into {output_path}",
    )


@app.command()
def render() -> None:
    """Render HTML dashboards from aggregated metrics."""
    report_path = Path("data/agg/report.json")
    build_dir = Path("build")
    public_dir = Path("public")
    template_dir = Path("app/templates")
    static_dir = Path("app/render/static")
    service = RenderService(
        report_path=report_path,
        template_dir=template_dir,
        static_dir=static_dir,
        build_dir=build_dir,
        public_dir=public_dir,
    )
    manifest = service.run()
    typer.echo(f"Rendered {len(manifest)} artifacts to {public_dir}")


@app.command()
def doctor() -> None:
    """Validate configuration and verify GitLab API connectivity."""
    try:
        settings = load_settings()
    except ValueError as exc:
        _handle_settings_error(exc)
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


def _patched_settings(settings: AppSettings, *, since: str | None, group: str | None) -> AppSettings:
    updates: dict[str, object] = {}
    if since:
        updates["report_since"] = since
    if group:
        updates["group_id_or_path"] = group
    if updates:
        settings = settings.model_copy(update=updates)
    return settings


def _handle_settings_error(exc: ValueError) -> NoReturn:
    typer.secho(f"Configuration error: {exc}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
