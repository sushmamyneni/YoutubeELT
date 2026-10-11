"""FastAPI transport layer exposing the business use cases over HTTP."""

import os
import secrets
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException

from .discovery import DiscoveryService
from .ports import SnapshotRepository
from .services import DashboardService
from .sqlite_repository import SQLiteSnapshotRepository
from .youtube_api import YouTubeApiError, YouTubeDataApiClient


def _default_database_path() -> Path:
    configured_path = os.getenv("YOUTUBE_DATABASE_PATH")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path(__file__).resolve().parents[3] / "youtube_trends.sqlite3"


def create_app(repository: SnapshotRepository | None = None) -> FastAPI:
    """Create the HTTP application, allowing a repository to be injected in tests."""
    snapshot_repository = repository or SQLiteSnapshotRepository(_default_database_path())
    snapshot_repository.initialize()
    dashboard_service = DashboardService(snapshot_repository)

    api = FastAPI(
        title="YouTube Trends Business API",
        version="0.1.0",
        description="Authenticated API for channel discovery and dashboard analytics.",
    )

    def require_api_token(authorization: str | None = Header(default=None)) -> None:
        expected_token = os.getenv("DASHBOARD_API_TOKEN", "")
        if not expected_token:
            raise HTTPException(status_code=503, detail="Business API token is not configured")

        scheme, separator, provided_token = (authorization or "").partition(" ")
        if (
            not separator
            or scheme.lower() != "bearer"
            or not secrets.compare_digest(provided_token, expected_token)
        ):
            raise HTTPException(
                status_code=401,
                detail="A valid bearer token is required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/dashboard")
    def get_dashboard(
        category: str | None = None,
        _: None = Depends(require_api_token),
    ) -> dict[str, Any]:
        return asdict(dashboard_service.get_data(category))

    @api.post("/discover")
    def discover(_: None = Depends(require_api_token)) -> dict[str, int]:
        api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
        if not api_key:
            raise HTTPException(status_code=503, detail="YouTube API key is not configured")

        discovery_service = DiscoveryService(
            YouTubeDataApiClient(api_key),
            snapshot_repository,
        )
        try:
            channel_count, video_count = discovery_service.discover_candidates()
        except YouTubeApiError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return {"channels_saved": channel_count, "videos_saved": video_count}

    return api


app = create_app()