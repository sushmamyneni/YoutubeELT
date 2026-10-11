import tempfile
import unittest
from pathlib import Path
from typing import Any

from youtube_trends_business.discovery import DiscoveryService
from youtube_trends_business.sqlite_repository import SQLiteSnapshotRepository


class FakeYouTubeDataSource:
    def __init__(self) -> None:
        self.search_queries: list[str] = []

    def search_videos(self, query: str, published_after: str, max_results: int) -> list[dict[str, Any]]:
        self.search_queries.append(query)
        return [
            {
                "id": {"videoId": "video-1"},
                "snippet": {
                    "channelId": "channel-1",
                    "channelTitle": "Example channel",
                    "title": "AI learning tools",
                    "publishedAt": "2026-10-10T00:00:00Z",
                    "thumbnails": {"medium": {"url": "https://example.test/video.jpg"}},
                },
            }
        ]

    def get_video_statistics(self, video_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {"video-1": {"viewCount": "1000", "likeCount": "100", "commentCount": "10"}}

    def get_channel_details(self, channel_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {
            "channel-1": {
                "id": "channel-1",
                "snippet": {
                    "title": "Example channel",
                    "thumbnails": {"default": {"url": "https://example.test/channel.jpg"}},
                },
                "statistics": {"subscriberCount": "500", "viewCount": "5000", "videoCount": "12"},
            }
        }


class FakeSnapshotRepository:
    def __init__(self) -> None:
        self.saved: tuple[Any, ...] | None = None

    def initialize(self) -> None:
        pass

    def save_discovery(self, *args: Any) -> tuple[int, int]:
        self.saved = args
        return 1, 1

    def load_snapshots(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return [], []


class DiscoveryServiceTests(unittest.TestCase):
    def test_discovery_uses_ports_and_saves_deduplicated_video(self):
        youtube = FakeYouTubeDataSource()
        repository = FakeSnapshotRepository()
        service = DiscoveryService(youtube, repository)

        result = service.discover_candidates()

        self.assertEqual(result, (1, 1))
        self.assertEqual(youtube.search_queries, ["technology", "artificial intelligence", "education"])
        self.assertIsNotNone(repository.saved)
        self.assertEqual(repository.saved[2].keys(), {"video-1"})
        self.assertEqual(
            repository.saved[1]["channel-1"],
            {"Technology", "AI", "Education"},
        )


class SQLiteSnapshotRepositoryTests(unittest.TestCase):
    def test_discovery_snapshots_round_trip_in_local_database(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = SQLiteSnapshotRepository(Path(temporary_directory) / "snapshots.sqlite3")
            repository.initialize()
            channel_details = {
                "channel-1": {
                    "snippet": {
                        "title": "Example channel",
                        "thumbnails": {"default": {"url": "https://example.test/channel.jpg"}},
                    },
                    "statistics": {"subscriberCount": "500", "viewCount": "5000", "videoCount": "12"},
                }
            }
            found_videos = {
                "video-1": {
                    "title": "AI learning tools",
                    "channel_id": "channel-1",
                    "channel_title": "Example channel",
                    "category": "AI",
                    "published_at": "2026-10-10T00:00:00Z",
                    "thumbnail_url": "https://example.test/video.jpg",
                }
            }

            result = repository.save_discovery(
                "2026-10-11T00:00:00+00:00",
                {"channel-1": {"AI"}},
                found_videos,
                {"video-1": {"viewCount": "1000", "likeCount": "100", "commentCount": "10"}},
                channel_details,
            )
            channels, videos = repository.load_snapshots()

        self.assertEqual(result, (1, 1))
        self.assertEqual(channels[0]["subscriber_count"], 500)
        self.assertEqual(channels[0]["categories"], "AI")
        self.assertEqual(videos[0]["view_count"], 1000)
        self.assertEqual(videos[0]["like_count"], 100)


if __name__ == "__main__":
    unittest.main()