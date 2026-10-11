"""Application use case for finding candidate channels and saving a snapshot."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .ports import SnapshotRepository, YouTubeDataSource


DISCOVERY_QUERIES = (
    ("Technology", "technology"),
    ("AI", "artificial intelligence"),
    ("Education", "education"),
)
DISCOVERY_WINDOW = timedelta(days=7)


class DiscoveryService:
    """Coordinate topic searches, metric lookups, and snapshot persistence."""

    def __init__(self, youtube: YouTubeDataSource, repository: SnapshotRepository) -> None:
        self._youtube = youtube
        self._repository = repository

    def discover_candidates(self) -> tuple[int, int]:
        published_after = (datetime.now(timezone.utc) - DISCOVERY_WINDOW).isoformat()
        found_videos: dict[str, dict[str, Any]] = {}
        categories_by_channel: dict[str, set[str]] = defaultdict(set)

        for category, query in DISCOVERY_QUERIES:
            for item in self._youtube.search_videos(query, published_after, 25):
                video_id = item.get("id", {}).get("videoId")
                snippet = item.get("snippet", {})
                channel_id = snippet.get("channelId")
                if not video_id or not channel_id:
                    continue
                found_videos.setdefault(
                    video_id,
                    {
                        "video_id": video_id,
                        "category": category,
                        "title": snippet.get("title", "Untitled video"),
                        "channel_id": channel_id,
                        "channel_title": snippet.get("channelTitle", "Unknown channel"),
                        "published_at": snippet.get("publishedAt"),
                        "thumbnail_url": snippet.get("thumbnails", {}).get("medium", {}).get("url"),
                    },
                )
                categories_by_channel[channel_id].add(category)

        video_ids = list(found_videos)
        if not video_ids:
            return 0, 0

        video_statistics = self._youtube.get_video_statistics(video_ids)
        channel_details = self._youtube.get_channel_details(list(categories_by_channel))
        captured_at = datetime.now(timezone.utc).date().isoformat() + "T00:00:00+00:00"
        return self._repository.save_discovery(
            captured_at,
            categories_by_channel,
            found_videos,
            video_statistics,
            channel_details,
        )