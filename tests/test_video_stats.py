import unittest

from video_stats import _weekly_change, latest_video_rows


class GrowthCalculationTests(unittest.TestCase):
    def test_weekly_change_normalizes_longer_snapshot_gap(self):
        snapshots = [
            {"captured_at": "2026-09-01T00:00:00+00:00", "subscriber_count": 10_000},
            {"captured_at": "2026-09-11T00:00:00+00:00", "subscriber_count": 11_000},
        ]

        weekly_change, weekly_percent = _weekly_change(snapshots, "subscriber_count")
        self.assertEqual(weekly_change, 700)
        self.assertAlmostEqual(weekly_percent, 7.0)

    def test_growth_is_unavailable_without_two_snapshots(self):
        snapshots = [{"captured_at": "2026-09-01T00:00:00+00:00", "subscriber_count": 10_000}]

        self.assertEqual(_weekly_change(snapshots, "subscriber_count"), (None, None))


class VideoSignalTests(unittest.TestCase):
    def test_engagement_uses_public_likes_and_comments(self):
        base_snapshot = {
            "video_id": "video-1",
            "channel_id": "channel-1",
            "thumbnail_url": None,
            "title": "AI learning tools",
            "channel_title": "Example channel",
            "category": "AI",
            "published_at": "2026-09-10T00:00:00Z",
            "like_count": 900,
            "comment_count": 100,
        }
        snapshots = [
            {**base_snapshot, "captured_at": "2026-09-10T00:00:00+00:00", "view_count": 9_500},
            {**base_snapshot, "captured_at": "2026-09-11T00:00:00+00:00", "view_count": 10_000},
        ]

        row = latest_video_rows(snapshots)[0]

        self.assertEqual(row["Engagement %"], 10.0)
        self.assertEqual(row["Views/day"], 500)


if __name__ == "__main__":
    unittest.main()