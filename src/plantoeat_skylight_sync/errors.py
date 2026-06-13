"""Errors for the Plan to Eat -> Skylight sync."""

from __future__ import annotations


class SyncError(Exception):
    """Any recoverable failure during a sync run (config, feed, or mapping)."""
