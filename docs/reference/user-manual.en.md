# GLMR User Manual (English)

## Overview

GLMR (GitLab Merge Request Metrics Toolkit) collects merge request data from GitLab, stores raw payloads for offline analysis, and produces aggregated reports that can be rendered into dashboards. This manual describes how to install, configure, operate, and maintain the toolkit for day-to-day use.

## System Requirements

- Python 3.13 or later
- Access to a GitLab instance with a personal access token that includes the `api` scope
- Network access from the runtime host to the GitLab API endpoint
- [uv](https://github.com/astral-sh/uv) for dependency management
- Optional: cron or another scheduler for automated collection runs

## Installation

1. Clone the repository and switch into the project directory.
2. Synchronize dependencies:
   ```bash
   uv sync --extra dev
   ```
3. (Optional) Activate the virtual environment created by uv if you prefer to run commands without prefixing them with `uv run`.

## Configuration

1. Copy the sample environment file and update it with values for your GitLab instance:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` and provide the required settings.

| Variable | Description |
| --- | --- |
| `GLMR_GITLAB_API_BASE` | Base URL for the GitLab REST API (default: `https://gitlab.com/api/v4`). |
| `GLMR_GITLAB_TOKEN` | Personal access token with `api` scope used for authenticated requests. |
| `GLMR_GROUP_ID_OR_PATH` | Numeric ID or full path of the GitLab group or project to crawl. |
| `GLMR_REPORT_SINCE` | ISO 8601 timestamp indicating the oldest merge request to include. |
| `GLMR_MAX_CONCURRENCY` | Maximum concurrent API requests used by collectors (tune to avoid rate limits). |
| `GLMR_PER_PAGE` | Page size for API pagination; defaults to 100. |
| `GLMR_COMMENT_DEDUP_MODE` | Strategy for merging duplicate comments (`author`, `thread`, or `none`). |
| `GLMR_LANG_PATTERNS_FILE` | Optional path to locale-specific review pattern overrides. |
| `GLMR_CACHE_DIR` | Directory where raw JSONL payloads are written (`data/raw/mr` by default). |

> **Tip:** Commit changes to `.env.example` whenever new configuration keys are introduced to keep onboarding smooth.

## Data Directories

- `data/raw/mr/`: JSONL cache of raw merge request payloads.
- `data/agg/report.json`: Aggregated metrics output used by renderers.
- `public/`: Rendered HTML, JavaScript, and assets produced by the `render` command.

Ensure these paths exist and are writable by the user running the CLI. Update the `.env` file if you prefer alternative locations.

## Running the CLI

Use `uv run` to execute the Typer CLI in a reproducible environment:

```bash
uv run glmr --help
```

Common workflows:

1. **Collect data**
   ```bash
   uv run glmr collect
   ```
   Downloads merge requests, discussions, notes, and reviewer assignments into the JSONL cache.

2. **Aggregate metrics**
   ```bash
   uv run glmr aggregate
   ```
   Produces windowed project and individual contributor metrics stored at `data/agg/report.json`.

3. **Render reports**
   ```bash
   uv run glmr render
   ```
   Builds static assets in `public/` for sharing insights.

4. **Verify configuration**
   ```bash
   uv run glmr doctor
   ```
   Validates environment variables and GitLab API connectivity.

## Scheduling and Automation

To keep metrics current, schedule recurring runs of the `collect` and `aggregate` commands using cron or a similar scheduler. For example:

```cron
0 * * * * cd /path/to/glmr && uv run glmr collect && uv run glmr aggregate
```

Pair automated jobs with monitoring to detect failures (non-zero exit codes or empty output files).

## Maintenance and Troubleshooting

- **Refreshing tokens:** Update `GLMR_GITLAB_TOKEN` before it expires to avoid authentication errors.
- **Handling rate limits:** Lower `GLMR_MAX_CONCURRENCY` or increase job spacing if the GitLab API returns 429 responses.
- **Resetting data:** Delete or archive the contents of `data/raw/mr/` and `data/agg/` before re-running `collect` if you need a clean slate.
- **Validating configuration:** Run `uv run glmr doctor` whenever settings change to confirm connectivity.
- **Checking logs:** CLI commands write operational logs to STDOUT/STDERR; capture them when running in automation for auditing.

## Getting Help

- Review the latest documentation in the repository (`docs/`) for architecture details and task notes.
- File issues in your internal tracker if you encounter bugs or missing metrics.
- Update the manuals when you introduce new commands or configuration options so all operators stay aligned.
