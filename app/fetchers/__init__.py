"""Fetchers for GitLab entities used during data collection."""

from . import discussions, groups, merge_requests, notes, projects, reviewers

__all__ = [
    "discussions",
    "groups",
    "merge_requests",
    "notes",
    "projects",
    "reviewers",
]
