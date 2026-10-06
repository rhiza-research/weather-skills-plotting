"""Errors raised while binding, defaulting, validating, or rendering a spec."""

from __future__ import annotations

from weather_skills_core.errors import DataError, UsageError

__all__ = ["DataError", "SpecError"]


class SpecError(UsageError):
    """A spec problem the agent can fix. The message starts with the JSON path."""
