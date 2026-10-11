import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from youtube_trends_business.api import create_app
from youtube_trends_business.sqlite_repository import SQLiteSnapshotRepository


class BusinessApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        repository = SQLiteSnapshotRepository(Path(self.temporary_directory.name) / "api.sqlite3")
        self.api = create_app(repository)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def request(self, method, path, headers=None):
        async def send_request():
            transport = httpx.ASGITransport(app=self.api)
            async with httpx.AsyncClient(transport=transport, base_url="http://business.test") as client:
                return await client.request(method, path, headers=headers)

        return asyncio.run(send_request())

    def test_health_check_does_not_require_authentication(self):
        response = self.request("GET", "/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_dashboard_requires_token_and_returns_serializable_data(self):
        with patch.dict(os.environ, {"DASHBOARD_API_TOKEN": "test-token"}):
            unauthorized = self.request("GET", "/dashboard")
            authorized = self.request(
                "GET",
                "/dashboard",
                {"Authorization": "Bearer test-token"},
            )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.json()["channel_rows"], [])
        self.assertIn("topic_terms", authorized.json())

    def test_discovery_requires_backend_youtube_key(self):
        with patch.dict(
            os.environ,
            {"DASHBOARD_API_TOKEN": "test-token", "YOUTUBE_API_KEY": ""},
        ):
            response = self.request(
                "POST",
                "/discover",
                {"Authorization": "Bearer test-token"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "YouTube API key is not configured")


if __name__ == "__main__":
    unittest.main()