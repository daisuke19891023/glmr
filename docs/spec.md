# GitLab MR Metrics Dashboard Specification

## Overview
This document defines the architecture and behavior for a GitLab Merge Request metrics collection and reporting tool. The tool ingests data from GitLab APIs, aggregates metrics for merge requests, reviews, and comments, and renders static HTML dashboards suitable for publication on GitLab Pages.

## Objectives
- Collect merge request activity across a GitLab group hierarchy (including subgroups) for repositories with merge requests enabled.
- Produce metrics summarizing merge requests, reviews, and comments over configurable time windows.
- Render static dashboards with filtering for people, projects, and date ranges, and publish to GitLab Pages with minimal diffs.
- Support scheduled, incremental runs via GitLab CI.

## Core Metrics
- **Merge Requests**: counts by creation, merge, and close status within the selected window.
- **Review Events**: counts of review requests and re-requests extracted from merge request system notes.
- **Reviewer Coverage**: distinct merge requests where a user is assigned as reviewer, including reviewed/unreviewed states when available.
- **Comments**: total user comments (non-system notes) and deduplicated counts by author or normalized body.

## GitLab API Usage
- `GET /groups/:id/projects?include_subgroups=true&with_merge_requests_enabled=true&archived=false` for project discovery.
- `GET /projects/:id/merge_requests?scope=all&state=all&updated_after=<ISO8601>` for incremental merge request retrieval.
- `GET /projects/:id/merge_requests/:iid/discussions` for comment metrics.
- `GET /projects/:id/merge_requests/:iid/notes` for review request events via system notes.
- `GET /projects/:id/merge_requests/:iid/reviewers` for reviewer status where supported.
- `GET /users/:id` or `GET /users?username=` for enriching user display information when necessary.

Pagination follows the `Link` headers or `X-Next-Page` responses until exhaustion. Requests must respect GitLab rate limiting (`429` handling and `Retry-After`).

## Architecture
```
app/
  cli.py                # Typer CLI: collect, aggregate, render, doctor
  config.py             # Pydantic settings sourced from environment/.env
  gitlab_client.py      # Shared httpx.AsyncClient wrapper with retries & pagination
  fetchers/             # GitLab API fetchers per entity
  models.py             # Pydantic models describing GitLab data
  store/                # Cache & filesystem utilities
  aggregate/            # Roll-up logic for time windows and pivots
  render/               # Jinja2 templates, filters, and diff-aware publish helpers
  templates/            # HTML templates (index, person pages, base layout)
```

### Data Flow
1. **Collect**: enumerate projects, fetch updated merge requests, and capture discussions, notes, and reviewer data. Cache merge request payloads keyed by `project_id#iid` and skip unchanged entries via `updated_at`.
2. **Aggregate**: transform raw data into time-windowed summaries for each person/project combination (7, 30, 90 days, and all-time).
3. **Render**: build HTML pages using Jinja2, embed JSON payloads for client-side filtering, compute content hashes, and publish only changed files to `public/` with a `manifest.json` for diff tracking.

### Storage Layout
- `data/raw/mr/*.jsonl`: raw merge request records with associated metrics and participant breakdowns.
- `data/agg/report.json`: aggregated metrics keyed by people, projects, and windows.
- `public/`: rendered HTML, JS, CSS, and manifest for GitLab Pages publication.

## Metrics Details
- **Review Request Detection**: parse system notes using configurable regex patterns (externalized in `config/review_patterns.yaml`) to handle locale differences.
- **Reviewer States**: prefer the dedicated reviewers endpoint; fall back to merge request payload fields if unavailable.
- **Comment Deduplication**: default to unique author counts; support normalized body hashing (trim code blocks, normalize whitespace, lowercase) when configured.
- **Recent Contributions**: per-person pages list recent merge requests where the user authored, reviewed, or commented.

## Rendering & Frontend
- Templates rendered with Jinja2 and served via GitLab Pages.
- Pages include a top-level dashboard (`index.html`) with filters for date window, people, and projects.
- Person detail pages (`people/<username>.html`) show per-repository breakdowns and recent contributions.
- Client-side filtering implemented with vanilla JavaScript reading embedded JSON data (`<script type="application/json">`).
- Static assets (`render/static/`) include CSS and JS for interactive filtering.

## CLI Commands
- `glmr collect --since <ISO8601> --group <path_or_id>`: run data collection and cache updates.
- `glmr aggregate`: build aggregated metrics JSON from raw cache files.
- `glmr render`: render templates, compare against `public/`, and update changed files only.
- `glmr doctor`: perform environment and API connectivity checks.

## CI/CD Strategy
- Scheduled GitLab CI pipeline runs `collect` and `aggregate` with cached dependencies via the `uv` container image.
- Rendering stage commits updated `public/` artifacts back to the repository.
- Final `pages` stage publishes the `public/` directory as GitLab Pages content.

## Configuration & Environment
Use `pydantic-settings` to manage environment variables, exposing defaults and documenting them in `.env.example`. Key variables include:
- `GITLAB_API_BASE` (default `https://gitlab.com/api/v4`)
- `GROUP_ID_OR_PATH`
- `GITLAB_TOKEN`
- `REPORT_SINCE`
- `MAX_CONCURRENCY`
- `COMMENT_DEDUP_MODE`
- `LANG_PATTERNS_FILE`

## Testing Approach
- Use `pytest` with `respx` to mock `httpx` requests for fetchers.
- Validate aggregation logic with deterministic fixture data.
- Snapshot or hash-based tests for rendered HTML outputs.
- Ensure no live network calls during automated tests.

## Security Considerations
- Authenticate using `PRIVATE-TOKEN` or `Authorization: Bearer` headers.
- Require `read_api` scope for data collection; `write_repository` for CI publishing steps if needed.
- Respect rate limits and avoid storing tokens in output artifacts.

## Future Enhancements
- GraphQL or keyset pagination for performance.
- Advanced ranking metrics and time-series visualizations.
- Multi-language UI support.
- Automated exclusion rules for bot accounts.
