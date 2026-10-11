"""HTTP client and response model for the separately deployed business API."""

from dataclasses import dataclass
from typing import Any

import httpx


class BusinessApiError(RuntimeError):
    """Raised when the business API is unavailable or rejects a request."""


@dataclass
class DashboardData:
    """Presentation-side view of the JSON payload returned by the API."""

    channel_snapshots: list[dict[str, Any]]
    video_snapshots: list[dict[str, Any]]
    channel_rows: list[dict[str, Any]]
    video_rows: list[dict[str, Any]]
    category_rows: list[dict[str, Any]]
    channel_performance: list[dict[str, Any]]
    category_options: list[str]
    growth_timeline: list[dict[str, Any]]
    topic_terms: list[tuple[str, int]]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DashboardData":
        payload["topic_terms"] = [tuple(term) for term in payload["topic_terms"]]
        return cls(**payload)


class BusinessApiClient:
    """Send authenticated dashboard and discovery requests to the backend."""

    def __init__(self, base_url: str, access_token: str, timeout: float = 30) -> None:
        self._base_url = base_url.rstrip("/")
        self._access_token = access_token
        self._timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {self._access_token}"}
        try:
            response = httpx.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                headers=headers,
                timeout=timeout or self._timeout,
            )
        except httpx.HTTPError as error:
            raise BusinessApiError("Could not connect to the business API.") from error

        if response.is_error:
            try:
                detail = response.json().get("detail", "Business API request failed")
            except ValueError:
                detail = "Business API request failed"
            raise BusinessApiError(str(detail))

        try:
            return response.json()
        except ValueError as error:
            raise BusinessApiError("Business API returned an invalid response.") from error

    def get_dashboard(self, category: str | None = None) -> DashboardData:
        params = {"category": category} if category else None
        payload = self._request("GET", "/dashboard", params=params)
        return DashboardData.from_payload(payload)

    def discover(self) -> tuple[int, int]:
        result = self._request("POST", "/discover", timeout=180)
        return result["channels_saved"], result["videos_saved"]