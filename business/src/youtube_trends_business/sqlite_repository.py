"""SQLite adapter implementing local snapshot persistence."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


class SQLiteSnapshotRepository:
    """Store channel and video observations without exposing SQL to the UI."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS channel_snapshots (
                    channel_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    thumbnail_url TEXT,
                    subscriber_count INTEGER,
                    view_count INTEGER,
                    video_count INTEGER,
                    categories TEXT NOT NULL,
                    PRIMARY KEY (channel_id, captured_at)
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS video_snapshots (
                    video_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    channel_title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    published_at TEXT,
                    thumbnail_url TEXT,
                    view_count INTEGER,
                    like_count INTEGER,
                    comment_count INTEGER,
                    PRIMARY KEY (video_id, captured_at)
                )"""
            )

    def save_discovery(
        self,
        captured_at: str,
        categories_by_channel: dict[str, set[str]],
        found_videos: dict[str, dict[str, Any]],
        video_statistics: dict[str, dict[str, Any]],
        channel_details: dict[str, dict[str, Any]],
    ) -> tuple[int, int]:
        with self._connection() as connection:
            for channel_id, item in channel_details.items():
                snippet = item.get("snippet", {})
                statistics = item.get("statistics", {})
                thumbnail_url = snippet.get("thumbnails", {}).get("default", {}).get("url")
                connection.execute(
                    """INSERT OR REPLACE INTO channel_snapshots
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        channel_id,
                        captured_at,
                        snippet.get("title", "Untitled channel"),
                        thumbnail_url,
                        _optional_int(statistics.get("subscriberCount")),
                        _optional_int(statistics.get("viewCount")),
                        _optional_int(statistics.get("videoCount")),
                        "|".join(sorted(categories_by_channel[channel_id])),
                    ),
                )

            for video_id, video in found_videos.items():
                statistics = video_statistics.get(video_id, {})
                connection.execute(
                    """INSERT OR REPLACE INTO video_snapshots
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        video_id,
                        captured_at,
                        video["title"],
                        video["channel_id"],
                        video["channel_title"],
                        video["category"],
                        video["published_at"],
                        video["thumbnail_url"],
                        _optional_int(statistics.get("viewCount")),
                        _optional_int(statistics.get("likeCount")),
                        _optional_int(statistics.get("commentCount")),
                    ),
                )
        return len(channel_details), len(found_videos)

    def load_snapshots(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with self._connection() as connection:
            connection.row_factory = sqlite3.Row
            channels = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM channel_snapshots ORDER BY captured_at"
                )
            ]
            videos = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM video_snapshots ORDER BY captured_at"
                )
            ]
        return channels, videos