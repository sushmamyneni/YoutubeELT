import unittest
from unittest.mock import patch

import httpx

from api_client import BusinessApiClient


class BusinessApiClientTests(unittest.TestCase):
    def test_dashboard_response_is_converted_to_presentation_model(self):
        payload = {
            "channel_snapshots": [],
            "video_snapshots": [],
            "channel_rows": [],
            "video_rows": [],
            "category_rows": [],
            "channel_performance": [],
            "category_options": ["AI"],
            "growth_timeline": [],
            "topic_terms": [["agents", 3]],
        }
        response = httpx.Response(
            200,
            json=payload,
            request=httpx.Request("GET", "http://business.test/dashboard"),
        )

        with patch("httpx.request", return_value=response):
            data = BusinessApiClient("http://business.test", "test-token").get_dashboard("AI")

        self.assertEqual(data.category_options, ["AI"])
        self.assertEqual(data.topic_terms, [("agents", 3)])


if __name__ == "__main__":
    unittest.main()