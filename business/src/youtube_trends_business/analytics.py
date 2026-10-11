"""Pure transformations for channel, video, category, and topic signals."""

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any


def weekly_change(snapshots: list[dict[str, Any]], field: str) -> tuple[int | None, float | None]:
    valid = [row for row in snapshots if row.get(field) is not None]
    if len(valid) < 2:
        return None, None

    latest = valid[-1]
    latest_time = datetime.fromisoformat(latest["captured_at"])
    cutoff = latest_time - timedelta(days=7)
    earlier = [row for row in valid[:-1] if datetime.fromisoformat(row["captured_at"]) <= cutoff]
    baseline = earlier[-1] if earlier else valid[0]
    elapsed_days = (latest_time - datetime.fromisoformat(baseline["captured_at"])).total_seconds() / 86400
    if elapsed_days <= 0:
        return None, None

    weekly_change = round((latest[field] - baseline[field]) * 7 / elapsed_days)
    weekly_percent = weekly_change / baseline[field] * 100 if baseline[field] else None
    return weekly_change, weekly_percent


def build_channel_rows(channel_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_channel: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in channel_snapshots:
        by_channel[snapshot["channel_id"]].append(snapshot)

    rows = []
    for channel_id, snapshots in by_channel.items():
        latest = snapshots[-1]
        subscriber_delta, subscriber_percent = weekly_change(snapshots, "subscriber_count")
        rows.append(
            {
                "Channel": latest["title"],
                "Channel ID": channel_id,
                "Thumbnail": latest["thumbnail_url"],
                "Categories": latest["categories"].replace("|", ", "),
                "Subscribers": latest["subscriber_count"],
                "Weekly subscribers": subscriber_delta,
                "Weekly growth %": subscriber_percent,
                "Views": latest["view_count"],
                "Videos": latest["video_count"],
                "URL": f"https://www.youtube.com/channel/{channel_id}",
            }
        )
    return rows


def latest_video_rows(video_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_video: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in video_snapshots:
        by_video[snapshot["video_id"]].append(snapshot)

    rows = []
    for video_id, snapshots in by_video.items():
        latest = snapshots[-1]
        views_per_day = None
        if latest["view_count"] is not None:
            if len(snapshots) > 1 and snapshots[0]["view_count"] is not None:
                days = (
                    datetime.fromisoformat(latest["captured_at"])
                    - datetime.fromisoformat(snapshots[0]["captured_at"])
                ).total_seconds() / 86400
                if days > 0:
                    views_per_day = round((latest["view_count"] - snapshots[0]["view_count"]) / days)
            if views_per_day is None and latest.get("published_at"):
                published = datetime.fromisoformat(latest["published_at"].replace("Z", "+00:00"))
                age_days = max((datetime.now(timezone.utc) - published).total_seconds() / 86400, 1)
                views_per_day = round(latest["view_count"] / age_days)
        views = latest["view_count"]
        interactions = (latest["like_count"] or 0) + (latest["comment_count"] or 0)
        rows.append(
            {
                "Video": latest["title"],
                "Channel": latest["channel_title"],
                "Channel ID": latest["channel_id"],
                "Category": latest["category"],
                "Thumbnail": latest["thumbnail_url"],
                "Views": views,
                "Views/day": views_per_day,
                "Engagement %": interactions / views * 100 if views else None,
                "Likes": latest["like_count"],
                "Comments": latest["comment_count"],
                "URL": f"https://www.youtube.com/watch?v={video_id}",
                "Video ID": video_id,
            }
        )
    return rows


def build_category_rows(video_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_video: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in video_snapshots:
        by_video[snapshot["video_id"]].append(snapshot)

    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"view_gain": 0, "video_count": 0})
    for snapshots in by_video.values():
        latest = snapshots[-1]
        category = latest["category"]
        totals[category]["video_count"] += 1
        if len(snapshots) > 1 and snapshots[-1]["view_count"] is not None and snapshots[0]["view_count"] is not None:
            totals[category]["view_gain"] += max(0, snapshots[-1]["view_count"] - snapshots[0]["view_count"])

    return [
        {
            "Category": category,
            "Tracked videos": values["video_count"],
            "Observed view gain": values["view_gain"] if values["view_gain"] else None,
        }
        for category, values in sorted(totals.items())
    ]


def build_channel_performance(
    channel_rows: list[dict[str, Any]], video_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    video_metrics: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"views_per_day": [], "engagement": []}
    )
    for video in video_rows:
        metrics = video_metrics[video["Channel ID"]]
        if video["Views/day"] is not None:
            metrics["views_per_day"].append(video["Views/day"])
        if video["Engagement %"] is not None:
            metrics["engagement"].append(video["Engagement %"])

    performance = []
    for channel in channel_rows:
        metrics = video_metrics[channel["Channel ID"]]
        performance.append(
            {
                **channel,
                "Views/day": round(sum(metrics["views_per_day"]) / len(metrics["views_per_day"]))
                if metrics["views_per_day"]
                else None,
                "Engagement %": sum(metrics["engagement"]) / len(metrics["engagement"])
                if metrics["engagement"]
                else None,
            }
        )
    return sorted(performance, key=lambda row: row["Views/day"] or 0, reverse=True)


def build_growth_timeline(
    channel_snapshots: list[dict[str, Any]], channel_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    channel_names = {
        row["Channel ID"]: row["Channel"]
        for row in sorted(channel_rows, key=lambda item: item["Subscribers"] or 0, reverse=True)[:5]
    }
    points_by_date: dict[str, dict[str, Any]] = {}
    for snapshot in channel_snapshots:
        channel_id = snapshot["channel_id"]
        if channel_id not in channel_names or snapshot["subscriber_count"] is None:
            continue
        captured_date = datetime.fromisoformat(snapshot["captured_at"])
        label = captured_date.strftime("%b %d")
        point = points_by_date.setdefault(snapshot["captured_at"][:10], {"Date": label})
        point[channel_names[channel_id]] = snapshot["subscriber_count"]
    return list(points_by_date.values())


def build_topic_terms(video_rows: list[dict[str, Any]]) -> list[tuple[str, int]]:
    stop_words = {
        "about", "after", "also", "are", "best", "but", "for", "from", "how", "into",
        "just", "more", "new", "not", "now", "one", "our", "out", "over", "the", "this",
        "today", "tutorial", "was", "what", "when", "with", "you", "your",
    }
    terms = Counter(
        term.lower()
        for video in video_rows
        for term in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{1,}", video["Video"])
        if term.lower() not in stop_words
    )
    return terms.most_common(12)