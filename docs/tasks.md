# Implementation Tasks

## Foundation
1. Initialize project structure under `app/` with CLI entry point, configuration, models, and GitLab client scaffolding.
2. Set up settings management using `pydantic-settings` and document required environment variables in `.env.example`.
3. Establish base Typer CLI with `collect`, `aggregate`, `render`, and `doctor` commands.

## Data Collection
1. Implement GitLab API client with httpx.AsyncClient, retry logic (tenacity), and pagination helpers.
2. Build fetchers for groups, projects, merge requests, discussions, notes, and reviewers, respecting rate limits and incremental sync parameters.
3. Create caching layer (JSONL storage) keyed by `project_id#iid` with `updated_at` guardrails to avoid redundant fetches.

## Aggregation
1. Model raw data using Pydantic for consistent parsing and validation.
2. Implement aggregation routines that compute metrics per person, project, and defined time windows (7/30/90 days and all-time).
3. Persist aggregated results to `data/agg/report.json` for downstream rendering.

## Rendering & Publishing
1. Create Jinja2 templates (`base.html.j2`, `index.html.j2`, `person.html.j2`) and static assets for filters and styling.
2. Implement rendering pipeline that writes to a build directory, computes hashes, and updates `public/` with changed files only.
3. Generate `public/manifest.json` capturing content hashes to support diff-aware deployment.

## Tooling & Quality
1. Configure pytest fixtures and respx mocks for deterministic HTTP testing.
2. Add tests covering fetchers, aggregation, rendering diffs, and CLI entry points.
3. Wire GitLab CI pipeline stages (`collect`, `render`, `pages`) using the `uv` container images and cache configuration.
