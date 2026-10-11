"""Application services that assemble use cases from storage and domain logic."""

from .analytics import (
    build_category_rows,
    build_channel_performance,
    build_channel_rows,
    build_growth_timeline,
    build_topic_terms,
    latest_video_rows,
)
from .discovery import DiscoveryService
from .models import DashboardData
from .ports import SnapshotRepository


class DashboardService:
    """Load, filter, and calculate the data consumed by presentation views."""

    def __init__(self, repository: SnapshotRepository) -> None:
        self._repository = repository

    def get_data(self, category: str | None = None) -> DashboardData:
        all_channels, all_videos = self._repository.load_snapshots()
        all_video_rows = latest_video_rows(all_videos)
        category_options = sorted({row["Category"] for row in all_video_rows})

        if category:
            all_videos = [row for row in all_videos if row["category"] == category]
            all_channels = [
                row for row in all_channels if category in row["categories"].split("|")
            ]

        channel_rows = build_channel_rows(all_channels)
        video_rows = latest_video_rows(all_videos)
        category_rows = build_category_rows(all_videos)
        channel_performance = build_channel_performance(channel_rows, video_rows)
        return DashboardData(
            channel_snapshots=all_channels,
            video_snapshots=all_videos,
            channel_rows=channel_rows,
            video_rows=video_rows,
            category_rows=category_rows,
            channel_performance=channel_performance,
            category_options=category_options,
            growth_timeline=build_growth_timeline(all_channels, channel_rows),
            topic_terms=build_topic_terms(
                sorted(video_rows, key=lambda row: row["Views/day"] or 0, reverse=True)
            ),
        )