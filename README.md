# GLMR – GitLab Merge Request Metrics Toolkit

This project collects merge request metadata from GitLab, persists raw payloads for offline analysis, and will eventually drive aggregation and dashboard rendering workflows. The current milestone focuses on establishing the collection foundation for data collection, aggregation, and publishing.

## Documentation

- [User Manual (English)](docs/reference/user-manual.en.md)
- [ユーザーマニュアル（日本語）](docs/reference/user-manual.ja.md)

These guides walk through installation, configuration, data management, and day-to-day operations.

## Getting Started

### Prerequisites

- Python 3.13+
- Access to a GitLab instance and a personal access token with API scope
- [uv](https://github.com/astral-sh/uv) for dependency management

### Installation

Install dependencies using uv:

```bash
uv sync --extra dev
```

### Configuration

1. Copy `.env.example` to `.env`.
2. Update the GitLab host, project path, access token, and output directories to match your environment.

### Running the CLI

Explore the available commands:

```bash
uv run glmr --help
```

## CLI Commands

| Command | Description |
| --- | --- |
| `glmr collect` | Collect merge requests, discussions, notes, and reviewers and write them to the JSONL cache under `data/raw/mr/`. |
| `glmr aggregate` | Aggregate cached merge request data into windowed project and people metrics written to `data/agg/report.json`. |
| `glmr render` | Render the aggregated report into static HTML/JS assets under `public/` with diff-aware publishing. |
| `glmr doctor` | Validate configuration and verify GitLab API connectivity. |

## Development Workflow

After making code changes run the mandatory checks:

```bash
uv run nox -s lint
uv run nox -s typing
```

Additional sessions are available in `noxfile.py` for formatting and tests.
