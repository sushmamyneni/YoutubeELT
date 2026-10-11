"""Adapter translating YouTube Data API requests into business-level results."""

from typing import Any

import requests


API_BASE = "https://youtube.googleapis.com/youtube/v3"


class YouTubeApiError(RuntimeError):
    """Raised when a YouTube API request cannot be completed or decoded."""


class YouTubeDataApiClient:
    """Talk to YouTube's REST API while hiding HTTP details from services."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _get(self, resource: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{API_BASE}/{resource}",
                params={**params, "key": self._api_key},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            # Do not include the request URL in errors; it contains the API key.
            raise YouTubeApiError(f"YouTube {resource} request failed") from error

    def search_videos(self, query: str, published_after: str, max_results: int) -> list[dict[str, Any]]:
        result = self._get(
            "search",
            {
                "part": "snippet",
                "type": "video",
                "order": "viewCount",
                "regionCode": "US",
                "relevanceLanguage": "en",
                "publishedAfter": published_after,
                "maxResults": max_results,
                "q": query,
            },
        )
        return result.get("items", [])

    def get_video_statistics(self, video_ids: list[str]) -> dict[str, dict[str, Any]]:
        statistics: dict[str, dict[str, Any]] = {}
        for start in range(0, len(video_ids), 50):
            result = self._get(
                "videos",
                {"part": "statistics", "id": ",".join(video_ids[start : start + 50])},
            )
            for item in result.get("items", []):
                statistics[item["id"]] = item.get("statistics", {})
        return statistics

    def get_channel_details(self, channel_ids: list[str]) -> dict[str, dict[str, Any]]:
        channels: dict[str, dict[str, Any]] = {}
        for start in range(0, len(channel_ids), 50):
            result = self._get(
                "channels",
                {"part": "snippet,statistics", "id": ",".join(channel_ids[start : start + 50])},
            )
            for item in result.get("items", []):
                channels[item["id"]] = item
        return channels