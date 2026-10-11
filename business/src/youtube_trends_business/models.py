"""Data returned by business services for presentation clients."""

from dataclasses import dataclass
from typing import Any


@dataclass
class DashboardData:
    """One consistent snapshot of the data needed to render a dashboard view."""

    channel_snapshots: list[dict[str, Any]]
    video_snapshots: list[dict[str, Any]]
    channel_rows: list[dict[str, Any]]
    video_rows: list[dict[str, Any]]
    category_rows: list[dict[str, Any]]
    channel_performance: list[dict[str, Any]]
    category_options: list[str]
    growth_timeline: list[dict[str, Any]]
    topic_terms: list[tuple[str, int]]