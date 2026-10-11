import os
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd
import requests
import streamlit as st

# Dashboard configuration: keeping the search scope fixed makes early results
# comparable while the local snapshot history is still being established.
API_BASE = "https://youtube.googleapis.com/youtube/v3"
DATABASE_PATH = Path(__file__).with_name("youtube_trends.sqlite3")
DISCOVERY_QUERIES = (
	("Technology", "technology"),
	("AI", "artificial intelligence"),
	("Education", "education"),
)
DISCOVERY_WINDOW = timedelta(days=7)


# Local persistence: SQLite keeps snapshots across app restarts without
# requiring a separate database server for this single-user first version.
def initialize_database() -> None:
	"""Create the two local tables used to track channel and video history."""
	with sqlite3.connect(DATABASE_PATH) as connection:
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


# YouTube API access: one helper centralizes timeouts, API-key handling, and
# HTTP error checks so every discovery request fails consistently.
def youtube_get(resource: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
	response = requests.get(
		f"{API_BASE}/{resource}",
		params={**params, "key": api_key},
		timeout=30,
	)
	response.raise_for_status()
	return response.json()


# Candidate discovery and snapshot collection: search recent popular videos,
# then fetch statistics in batches because the API accepts multiple IDs per call.
def discover_candidates(api_key: str) -> tuple[int, int]:
	published_after = (datetime.now(timezone.utc) - DISCOVERY_WINDOW).isoformat()
	found_videos: dict[str, dict[str, Any]] = {}
	categories_by_channel: dict[str, set[str]] = defaultdict(set)

	for category, query in DISCOVERY_QUERIES:
		result = youtube_get(
			"search",
			{
				"part": "snippet",
				"type": "video",
				"order": "viewCount",
				"regionCode": "US",
				"relevanceLanguage": "en",
				"publishedAfter": published_after,
				"maxResults": 25,
				"q": query,
			},
			api_key,
		)
		for item in result.get("items", []):
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

	video_stats: dict[str, dict[str, Any]] = {}
	for start in range(0, len(video_ids), 50):
		result = youtube_get(
			"videos",
			{"part": "statistics", "id": ",".join(video_ids[start : start + 50])},
			api_key,
		)
		for item in result.get("items", []):
			video_stats[item["id"]] = item.get("statistics", {})

	channel_ids = list(categories_by_channel)
	channel_details: dict[str, dict[str, Any]] = {}
	# Batch channel detail lookups too, keeping requests below the API's ID limit.
	for start in range(0, len(channel_ids), 50):
		result = youtube_get(
			"channels",
			{"part": "snippet,statistics", "id": ",".join(channel_ids[start : start + 50])},
			api_key,
		)
		for item in result.get("items", []):
			channel_details[item["id"]] = item

	# Store one canonical timestamp per UTC day so repeated runs replace today's
	# data instead of creating tiny intervals that would distort growth rates.
	captured_at = datetime.now(timezone.utc).date().isoformat() + "T00:00:00+00:00"
	with sqlite3.connect(DATABASE_PATH) as connection:
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
			statistics = video_stats.get(video_id, {})
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


# API counts may be absent for hidden or unavailable statistics; preserving
# those as None avoids pretending that a missing count is actually zero.
def _optional_int(value: Any) -> int | None:
	return int(value) if value is not None else None


# Snapshot loading: return ordinary dictionaries so metric calculations and
# Streamlit tables can work with the same simple, database-independent shape.
def load_snapshots() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
	with sqlite3.connect(DATABASE_PATH) as connection:
		connection.row_factory = sqlite3.Row
		channels = [dict(row) for row in connection.execute(
			"SELECT * FROM channel_snapshots ORDER BY captured_at"
		)]
		videos = [dict(row) for row in connection.execute(
			"SELECT * FROM video_snapshots ORDER BY captured_at"
		)]
	return channels, videos


# Metric preparation: normalize the change to a weekly rate so snapshots taken
# more than seven days apart remain comparable; with one sample, report no rate.
def _weekly_change(snapshots: list[dict[str, Any]], field: str) -> tuple[int | None, float | None]:
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

	change = latest[field] - baseline[field]
	weekly_change = round(change * 7 / elapsed_days)
	base_count = baseline[field]
	weekly_percent = (weekly_change / base_count * 100) if base_count else None
	return weekly_change, weekly_percent


# Channel table rows: collapse each channel's history to its latest public
# totals while attaching any weekly subscriber change supported by the history.
def build_channel_rows(channel_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
	by_channel: dict[str, list[dict[str, Any]]] = defaultdict(list)
	for snapshot in channel_snapshots:
		by_channel[snapshot["channel_id"]].append(snapshot)

	rows = []
	for channel_id, snapshots in by_channel.items():
		latest = snapshots[-1]
		subscriber_delta, subscriber_percent = _weekly_change(snapshots, "subscriber_count")
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


# Video signals: calculate engagement from public likes/comments and estimate
# daily view velocity from repeated snapshots, falling back to lifetime video age.
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
				"Engagement %": (interactions / views * 100) if views else None,
				"Likes": latest["like_count"],
				"Comments": latest["comment_count"],
				"URL": f"https://www.youtube.com/watch?v={video_id}",
				"Video ID": video_id,
			}
		)
	return rows


# Category signals: sum observed view gains by discovered topic. When there is
# no repeated video observation, the UI can use candidate counts as a baseline.
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


# Channel-level video performance: average each channel's candidate-video
# velocity and engagement so channels can be compared using the same sample.
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


# Timeline data: limit the chart to the five largest tracked channels so their
# subscriber histories stay readable in a compact dashboard panel.
def build_growth_timeline(
	channel_snapshots: list[dict[str, Any]], channel_rows: list[dict[str, Any]]
) -> pd.DataFrame:
	channel_names = {
		row["Channel ID"]: row["Channel"]
		for row in sorted(channel_rows, key=lambda item: item["Subscribers"] or 0, reverse=True)[:5]
	}
	points = [
		{
			"Date": datetime.fromisoformat(snapshot["captured_at"]).strftime("%b %d"),
			"Channel": channel_names[snapshot["channel_id"]],
			"Subscribers": snapshot["subscriber_count"],
		}
		for snapshot in channel_snapshots
		if snapshot["channel_id"] in channel_names and snapshot["subscriber_count"] is not None
	]
	if not points:
		return pd.DataFrame()
	return pd.DataFrame(points).pivot(index="Date", columns="Channel", values="Subscribers").reset_index()


# Topic clues: count informative words in fast-moving video titles; this is a
# lightweight clue generator, not a causal model of why a channel is growing.
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


# Dashboard UI: render navigation, filters, headline metrics, charts, tables,
# and discovery controls in one local Streamlit app.
def render_dashboard() -> None:
	st.set_page_config(
		page_title="YouTube Signals",
		page_icon="YT",
		layout="wide",
		initial_sidebar_state="expanded",
	)
	st.markdown(
		"""<style>
		:root { color-scheme: dark; }
		.stApp { background: #0a101a; color: #dce5f2; }
		[data-testid="stHeader"] { background: rgba(10, 16, 26, 0.92); }
		.block-container { padding: 1.15rem 1.5rem 2rem; max-width: 1680px; }
		[data-testid="stSidebar"] { background: #0c1421; border-right: 1px solid #1e2a3c; }
		[data-testid="stSidebar"] { width: 15rem !important; min-width: 15rem !important; }
		[data-testid="stSidebar"] > div { padding-top: 1.1rem; }
		h1, h2, h3, h4 { color: #eff5ff; letter-spacing: 0; }
		[data-testid="stHeading"] h1, .stApp h1 { font-size: 1.55rem !important; line-height: 1.2 !important; margin-bottom: 0.1rem !important; }
		[data-testid="stHeading"] h2, .stApp h2 { font-size: 1.05rem !important; line-height: 1.25 !important; }
		[data-testid="stCaptionContainer"] { color: #8b9bb2; }
		[data-testid="stMetric"] { background: #111c2c; border: 1px solid #24334a; padding: 0.85rem 1rem; border-radius: 6px; min-height: 106px; }
		[data-testid="stMetricLabel"] { color: #9babc2; }
		[data-testid="stMetricValue"] { color: #f4f7fb; font-size: 1.6rem; }
		[data-testid="stMetricDelta"] { font-size: 0.78rem; }
		[data-testid="stVerticalBlockBorderWrapper"] { background: #101a29; border-color: #24334a; border-radius: 7px; }
		[data-testid="stVerticalBlockBorderWrapper"] > div { padding: 0.85rem 1rem; }
		[data-testid="stDataFrame"] { border: 1px solid #202d40; border-radius: 5px; }
		[data-testid="stSelectbox"] label, [data-testid="stRadio"] label { color: #aebbd0; }
		[data-testid="stRadio"] [role="radiogroup"] { gap: 0.25rem; }
		[data-testid="stRadio"] [role="radio"] { padding: 0.55rem 0.7rem; border-radius: 5px; }
		[data-testid="stRadio"] [role="radio"]:has(input:checked) { background: #173653; color: #74d5cb; }
		div.stButton > button { border-radius: 5px; border: 1px solid #197d78; background: #126b68; color: #f4ffff; }
		div.stButton > button:hover { background: #17817b; color: #fff; border: 1px solid #43aaa0; }
		[data-testid="stMarkdownContainer"] a { color: #78c8ff; }
		.signal-brand { display:flex; align-items:center; gap:10px; padding: 0.3rem 0.2rem 1.1rem; color:#ecf4ff; font-weight:700; font-size:0.95rem; }
		.signal-mark { display:grid; place-items:center; width:28px; height:22px; border-radius:5px; background:#e3424f; color:white; font-size:0.65rem; }
		.signal-subtitle { color:#8393aa; font-size:0.78rem; font-weight:400; }
		.dashboard-title { color:#eff5ff; font-size:1.45rem; font-weight:700; line-height:1.2; }
		.dashboard-subtitle { color:#8393aa; font-size:0.78rem; margin-top:0.15rem; }
		.filter-label { color:#7788a0; font-size:0.65rem; text-transform:uppercase; }
		.filter-value { color:#dce5f2; font-size:0.82rem; padding-top:0.22rem; }
		.panel-kicker { color:#788ba4; font-size:0.68rem; text-transform:uppercase; }
		@media (max-width: 750px) { .block-container { padding: 0.8rem 0.75rem 1.5rem; } }
		</style>""",
		unsafe_allow_html=True,
	)

	initialize_database()
	api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
	# Load all snapshots once, then derive each view from these in-memory rows.
	channel_snapshots, video_snapshots = load_snapshots()
	all_channel_rows = build_channel_rows(channel_snapshots)
	all_video_rows = latest_video_rows(video_snapshots)
	category_options = sorted({row["Category"] for row in all_video_rows})

	with st.sidebar:
		st.markdown(
			'<div class="signal-brand"><span class="signal-mark">YT</span><span>YouTube Signals<br><span class="signal-subtitle">Creator intelligence</span></span></div>',
			unsafe_allow_html=True,
		)
		page = st.radio(
			"Dashboard section",
			["Overview", "Trending channels", "Category trends", "Channel explorer", "Top videos", "Insights"],
			label_visibility="collapsed",
		)

	# Keep discovery beside the main filters rather than in navigation, and read
	# credentials from the environment so the API key never appears in the UI.
	main_columns = st.columns([1.8, 0.8, 0.8, 0.8, 0.8], vertical_alignment="bottom")
	with main_columns[0]:
		st.markdown(
			'<div class="dashboard-title">YouTube Trending Channels</div><div class="dashboard-subtitle">Fast-growing creators and emerging trends in US technology, AI, and education</div>',
			unsafe_allow_html=True,
		)
	with main_columns[1]:
		st.markdown('<div class="filter-label">Market</div><div class="filter-value">United States</div>', unsafe_allow_html=True)
	with main_columns[2]:
		selected_category = st.selectbox("Category", ["All categories", *category_options], label_visibility="visible")
	with main_columns[3]:
		st.markdown('<div class="filter-label">Discovery window</div><div class="filter-value">Past 7 days</div>', unsafe_allow_html=True)
	with main_columns[4]:
		if st.button("Discover", disabled=not api_key, width="stretch", help="Set YOUTUBE_API_KEY in the environment to enable discovery."):
			try:
				with st.spinner("Searching YouTube and saving today's metrics..."):
					channel_count, video_count = discover_candidates(api_key)
				st.success(f"Saved {channel_count} channels and {video_count} candidate videos.")
				st.rerun()
			except (requests.RequestException, ValueError, KeyError) as error:
				st.error(f"YouTube request failed: {error}")
	if not api_key:
		st.caption("Discovery is disabled. Set YOUTUBE_API_KEY in the terminal environment to enable it.")

	if selected_category != "All categories":
		# Apply one category filter consistently to channel, video, and category views.
		video_snapshots = [row for row in video_snapshots if row["category"] == selected_category]
		channel_snapshots = [
			row for row in channel_snapshots if selected_category in row["categories"].split("|")
		]

	channel_rows = build_channel_rows(channel_snapshots)
	video_rows = latest_video_rows(video_snapshots)
	category_rows = build_category_rows(video_snapshots)
	channel_performance = build_channel_performance(channel_rows, video_rows)
	growth_rows = [row["Weekly growth %"] for row in channel_rows if row["Weekly growth %"] is not None]
	average_growth = sum(growth_rows) / len(growth_rows) if growth_rows else None
	views_per_day = [row["Views/day"] for row in video_rows if row["Views/day"] is not None]
	average_views_per_day = sum(views_per_day) / len(views_per_day) if views_per_day else None
	emerging_count = sum(1 for row in channel_rows if row["Subscribers"] is not None and row["Subscribers"] < 100_000)
	latest_capture = max((row["captured_at"] for row in channel_snapshots), default=None)

	metric_columns = st.columns(4)
	metric_columns[0].metric("Trending channels", len(channel_rows))
	metric_columns[1].metric(
		"Avg. subscriber growth",
		f"{average_growth:+.1f}%" if average_growth is not None else "Building history",
		"7-day rate" if average_growth is not None else None,
	)
	metric_columns[2].metric(
		"Avg. views per day",
		f"{average_views_per_day:,.0f}" if average_views_per_day is not None else "No video data",
	)
	metric_columns[3].metric("Emerging creators", emerging_count, "under 100k subscribers")
	if latest_capture:
		st.caption(
			f"Latest snapshot: {datetime.fromisoformat(latest_capture).strftime('%b %d, %Y')}  |  "
			"Engagement is likes plus comments divided by views on discovered videos."
		)

	if page == "Overview":
		# Overview prioritizes cross-cutting signals; detailed tables live in the
		# dedicated navigation sections below.
		upper_left, upper_right = st.columns([1.65, 1], gap="small")
		with upper_left, st.container(border=True):
			st.subheader("Subscriber history")
			timeline = build_growth_timeline(channel_snapshots, channel_rows)
			if not timeline.empty and timeline["Date"].nunique() >= 2:
				series = [column for column in timeline.columns if column != "Date"]
				st.line_chart(timeline, x="Date", y=series, height=230, width="stretch")
			else:
				# A single date is a baseline, not a trend, so avoid drawing a misleading line.
				st.info("Baseline captured. Run discovery on another day to reveal subscriber growth trends.")
		with upper_right, st.container(border=True):
			st.subheader("Channels by category")
			if category_rows:
				category_frame = pd.DataFrame(category_rows).set_index("Category")[["Tracked videos"]]
				st.bar_chart(category_frame, color="#41c7b2", height=230, width="stretch")
				st.caption("Count of discovered videos in each topic.")
			else:
				st.info("Category signals appear after discovery.")

		lower_left, lower_right = st.columns([1.65, 1], gap="small")
		with lower_left, st.container(border=True):
			st.subheader("Top channels by video velocity")
			if channel_performance:
				leaderboard = pd.DataFrame(channel_performance).head(10)
				st.dataframe(
					leaderboard[["Channel", "Categories", "Subscribers", "Weekly growth %", "Views/day", "URL"]],
					width="stretch",
					hide_index=True,
					column_config={
						"Weekly growth %": st.column_config.NumberColumn("7d growth %", format="%+.1f%%"),
						"Views/day": st.column_config.NumberColumn("Views/day", format="%d"),
						"URL": st.column_config.LinkColumn("Channel", display_text="Open"),
					},
				)
				st.caption("Ranked by average views per day across discovered videos; subscriber growth needs repeat snapshots.")
			else:
				st.info("Channel rankings appear after discovery.")
		with lower_right, st.container(border=True):
			st.subheader("Channel spotlight")
			if channel_performance:
				channel_choices = {
					f"{row['Channel']} ({row['Channel ID'][-4:]})": row["Channel ID"]
					for row in channel_performance
				}
				selected_channel_label = st.selectbox("Select channel", list(channel_choices), label_visibility="collapsed")
				selected_channel_id = channel_choices[selected_channel_label]
				spotlight = next(row for row in channel_performance if row["Channel ID"] == selected_channel_id)
				st.markdown(f"### {spotlight['Channel']}")
				st.caption(spotlight["Categories"] or "No topic label")
				spotlight_metrics = st.columns(2)
				spotlight_metrics[0].metric("Subscribers", f"{spotlight['Subscribers']:,}" if spotlight["Subscribers"] is not None else "Hidden")
				spotlight_metrics[1].metric("Views/day", f"{spotlight['Views/day']:,}" if spotlight["Views/day"] is not None else "Collecting")
				st.link_button("Open channel", spotlight["URL"], width="stretch")
			else:
				st.info("A channel spotlight will appear after discovery.")

		bottom_left, bottom_right = st.columns([1, 1], gap="small")
		with bottom_left, st.container(border=True):
			st.subheader("Channel size distribution")
			subscriber_values = [row["Subscribers"] for row in channel_rows if row["Subscribers"] is not None]
			if subscriber_values:
				bands = pd.cut(
					pd.Series(subscriber_values),
					bins=[0, 10_000, 100_000, 1_000_000, 10_000_000, float("inf")],
					labels=["Under 10k", "10k-100k", "100k-1m", "1m-10m", "10m+"],
					include_lowest=True,
				).value_counts(sort=False)
				st.bar_chart(bands, color="#528cff", height=190, width="stretch")
			else:
				st.info("Subscriber counts are unavailable for this sample.")
		with bottom_right, st.container(border=True):
			st.subheader("Videos driving attention")
			if video_rows:
				video_frame = pd.DataFrame(video_rows).sort_values("Views/day", ascending=False, na_position="last").head(5)
				st.dataframe(
					video_frame[["Thumbnail", "Video", "Channel", "Views/day", "URL"]],
					width="stretch",
					hide_index=True,
					column_config={
						"Thumbnail": st.column_config.ImageColumn("", width="small"),
						"Views/day": st.column_config.NumberColumn("Views/day", format="%d"),
						"URL": st.column_config.LinkColumn("Video", display_text="Watch"),
					},
				)
			else:
				st.info("Recent video signals appear after discovery.")
	elif page == "Trending channels":
		# Show the full channel comparison table, leaving growth blank until repeat
		# snapshots provide enough evidence to calculate it.
		with st.container(border=True):
			st.subheader("Trending channel leaders")
			if channel_performance:
				st.dataframe(
					pd.DataFrame(channel_performance)[["Thumbnail", "Channel", "Categories", "Subscribers", "Weekly subscribers", "Weekly growth %", "Views/day", "Engagement %", "URL"]],
					width="stretch",
					hide_index=True,
					column_config={
						"Thumbnail": st.column_config.ImageColumn("", width="small"),
						"Weekly growth %": st.column_config.NumberColumn("7d growth %", format="%+.1f%%"),
						"Engagement %": st.column_config.NumberColumn("Engagement %", format="%.2f%%"),
						"URL": st.column_config.LinkColumn("Channel", display_text="Open"),
					},
				)
			else:
				st.info("Run discovery to build the channel list.")
			st.caption("Growth rates are based on saved snapshots and remain blank until a channel has observations on separate days.")
	elif page == "Category trends":
		# Prefer actual observed view gain; use sample size only as an explicitly
		# limited first-run signal before repeat snapshots exist.
		with st.container(border=True):
			st.subheader("Category momentum")
			if category_rows:
				category_frame = pd.DataFrame(category_rows)
				metric = "Observed view gain" if category_frame["Observed view gain"].notna().any() else "Tracked videos"
				st.bar_chart(category_frame.set_index("Category")[[metric]], color="#41c7b2", height=350, width="stretch")
				st.dataframe(category_frame, width="stretch", hide_index=True)
				st.caption("Until repeat video snapshots exist, this view shows the size of the discovered sample rather than category-wide YouTube popularity.")
			else:
				st.info("Category signals appear after discovery.")
	elif page == "Channel explorer":
		# Let a user inspect one candidate channel and the specific videos found for it.
		with st.container(border=True):
			st.subheader("Explore a channel")
			if channel_performance:
				channel_choices = {
					f"{row['Channel']} ({row['Channel ID'][-4:]})": row["Channel ID"]
					for row in channel_performance
				}
				selected_label = st.selectbox("Channel", list(channel_choices))
				selected_id = channel_choices[selected_label]
				spotlight = next(row for row in channel_performance if row["Channel ID"] == selected_id)
				st.subheader(spotlight["Channel"])
				stats = st.columns(4)
				stats[0].metric("Subscribers", f"{spotlight['Subscribers']:,}" if spotlight["Subscribers"] is not None else "Hidden")
				stats[1].metric("Weekly growth", f"{spotlight['Weekly growth %']:+.1f}%" if spotlight["Weekly growth %"] is not None else "Building history")
				stats[2].metric("Views/day", f"{spotlight['Views/day']:,}" if spotlight["Views/day"] is not None else "Collecting")
				stats[3].metric("Engagement", f"{spotlight['Engagement %']:.2f}%" if spotlight["Engagement %"] is not None else "Unavailable")
				st.caption(spotlight["Categories"])
				st.link_button("Open channel", spotlight["URL"])
				spotlight_videos = [row for row in video_rows if row["Channel ID"] == selected_id]
				if spotlight_videos:
					st.dataframe(
						pd.DataFrame(spotlight_videos)[["Thumbnail", "Video", "Views", "Views/day", "Engagement %", "URL"]],
						width="stretch",
						hide_index=True,
						column_config={"Thumbnail": st.column_config.ImageColumn("", width="small"), "URL": st.column_config.LinkColumn("Video", display_text="Watch")},
					)
			else:
				st.info("Run discovery to add channels to the explorer.")
	elif page == "Top videos":
		# Rank videos by daily velocity to compare newer and older uploads more fairly.
		with st.container(border=True):
			st.subheader("Top videos by daily view velocity")
			if video_rows:
				video_frame = pd.DataFrame(video_rows).sort_values("Views/day", ascending=False, na_position="last")
				st.dataframe(
					video_frame[["Thumbnail", "Video", "Channel", "Category", "Views", "Views/day", "Engagement %", "URL"]],
					width="stretch",
					hide_index=True,
					column_config={
						"Thumbnail": st.column_config.ImageColumn("", width="small"),
						"Views/day": st.column_config.NumberColumn("Views/day", format="%d"),
						"Engagement %": st.column_config.NumberColumn("Engagement %", format="%.2f%%"),
						"URL": st.column_config.LinkColumn("Video", display_text="Watch"),
					},
				)
				st.caption("Views/day uses observed view increases when repeat snapshots exist; otherwise it is lifetime views divided by video age.")
			else:
				st.info("Run discovery to find recent videos.")
	elif page == "Insights":
		# Surface repeated title terms as prompts for investigation, while making
		# the correlation-versus-causation limitation visible to dashboard users.
		with st.container(border=True):
			st.subheader("Topics appearing in high-velocity video titles")
			topics = build_topic_terms(sorted(video_rows, key=lambda row: row["Views/day"] or 0, reverse=True))
			if topics:
				maximum = max(count for _, count in topics)
				cloud = "".join(
					f'<span style="font-size:{0.85 + count / maximum * 1.0:.2f}rem;color:{"#58d2c0" if index % 3 == 0 else "#e3ebf7" if index % 3 == 1 else "#76a9ff"};padding:0.25rem 0.6rem;display:inline-block">{term}</span>'
					for index, (term, count) in enumerate(topics)
				)
				st.markdown(f'<div style="line-height:2.2">{cloud}</div>', unsafe_allow_html=True)
				st.caption("Keyword counts come from discovered video titles. They suggest topics to investigate, but do not establish why a channel grew.")
			else:
				st.info("Topic signals appear after video discovery.")
		with st.container(border=True):
			st.subheader("Measurement notes")
			st.markdown(
				"- Discovery covers three fixed searches and is not a complete YouTube-wide ranking.\n"
				"- Subscriber growth requires repeat daily snapshots; public subscriber totals may be rounded.\n"
				"- Engagement uses public likes and comments on discovered videos, not channel analytics.\n"
				"- Video-title topics are correlation clues, not causal explanations."
			)


if __name__ == "__main__":
	# Run the Streamlit UI only when this file is launched as the app entry point.
	render_dashboard()