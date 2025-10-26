# GLMR – GitLab Merge Request Metrics Toolkit

This project collects merge request metadata from GitLab, persists raw payloads for offline analysis, and will eventually drive aggregation and dashboard rendering workflows. The current milestone focuses on establishing the collection foundation.

## Getting Started

1. Install dependencies using [uv](https://github.com/astral-sh/uv):
   ```bash
   uv sync --extra dev
   ```
2. Copy `.env.example` to `.env` and update the values for your GitLab instance and access token.
3. Run one of the Typer CLI commands:
   ```bash
   uv run glmr --help
   ```

## CLI Commands

| Command | Description |
| --- | --- |
| `glmr collect` | Collect merge requests, discussions, notes, and reviewers and write them to the JSONL cache under `data/raw/mr/`. |
| `glmr aggregate` | Placeholder for the upcoming aggregation pipeline. |
| `glmr render` | Placeholder for the upcoming rendering pipeline. |
| `glmr doctor` | Validate configuration and verify GitLab API connectivity. |

## Development Workflow

After making code changes run the mandatory checks:

```bash
uv run nox -s lint
uv run nox -s typing
```

Additional sessions are available in `noxfile.py` for formatting and tests.
