"""Interfaces that keep business workflows independent of network and storage details."""

from typing import Any, Protocol


class YouTubeDataSource(Protocol):
    """Operations the discovery workflow needs from a YouTube API adapter."""

    def search_videos(self, query: str, published_after: str, max_results: int) -> list[dict[str, Any]]: ...

    def get_video_statistics(self, video_ids: list[str]) -> dict[str, dict[str, Any]]: ...

    def get_channel_details(self, channel_ids: list[str]) -> dict[str, dict[str, Any]]: ...


class SnapshotRepository(Protocol):
    """Persistence operations used by discovery and dashboard query services."""

    def initialize(self) -> None: ...

    def save_discovery(
        self,
        captured_at: str,
        categories_by_channel: dict[str, set[str]],
        found_videos: dict[str, dict[str, Any]],
        video_statistics: dict[str, dict[str, Any]],
        channel_details: dict[str, dict[str, Any]],
    ) -> tuple[int, int]: ...

    def load_snapshots(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]: ...