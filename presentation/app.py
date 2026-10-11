"""Streamlit presentation layer for YouTube channel intelligence."""

import os

import pandas as pd
import streamlit as st

from api_client import BusinessApiClient, BusinessApiError, DashboardData


def _render_styles() -> None:
    """Apply the dashboard's dark visual theme and compact analytics layout."""
    st.markdown(
        """<style>
        :root { color-scheme: dark; }
        .stApp { background: #0a101a; color: #dce5f2; }
        [data-testid="stHeader"] { background: rgba(10, 16, 26, 0.92); }
        .block-container { padding: 3.25rem 1.5rem 2rem; max-width: 1680px; }
        [data-testid="stSidebar"] { background: #0c1421; border-right: 1px solid #1e2a3c; width: 15rem !important; min-width: 15rem !important; }
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
        .dashboard-title { color:#eff5ff; font-size:1.45rem; font-weight:700; line-height:1.35; padding-top:0.15rem; overflow:visible; }
        .dashboard-subtitle { color:#8393aa; font-size:0.78rem; margin-top:0.15rem; }
        .filter-label { color:#7788a0; font-size:0.65rem; text-transform:uppercase; }
        .filter-value { color:#dce5f2; font-size:0.82rem; padding-top:0.22rem; }
        @media (max-width: 750px) { .block-container { padding: 2.75rem 0.75rem 1.5rem; } }
        </style>""",
        unsafe_allow_html=True,
    )


def _render_overview(data: DashboardData) -> None:
    """Render the overview's summary charts, leaderboards, and spotlight."""
    upper_left, upper_right = st.columns([1.65, 1], gap="small")
    with upper_left, st.container(border=True):
        st.subheader("Subscriber history")
        timeline = pd.DataFrame(data.growth_timeline)
        if not timeline.empty and timeline["Date"].nunique() >= 2:
            series = [column for column in timeline.columns if column != "Date"]
            st.line_chart(timeline, x="Date", y=series, height=230, width="stretch")
        else:
            st.info("Baseline captured. Run discovery on another day to reveal subscriber growth trends.")
    with upper_right, st.container(border=True):
        st.subheader("Channels by category")
        if data.category_rows:
            category_frame = pd.DataFrame(data.category_rows).set_index("Category")[["Tracked videos"]]
            st.bar_chart(category_frame, color="#41c7b2", height=230, width="stretch")
            st.caption("Count of discovered videos in each topic.")
        else:
            st.info("Category signals appear after discovery.")

    lower_left, lower_right = st.columns([1.65, 1], gap="small")
    with lower_left, st.container(border=True):
        st.subheader("Top channels by video velocity")
        if data.channel_performance:
            leaderboard = pd.DataFrame(data.channel_performance).head(10)
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
        if data.channel_performance:
            choices = {
                f"{row['Channel']} ({row['Channel ID'][-4:]})": row["Channel ID"]
                for row in data.channel_performance
            }
            label = st.selectbox("Select channel", list(choices), label_visibility="collapsed")
            channel = next(row for row in data.channel_performance if row["Channel ID"] == choices[label])
            st.markdown(f"### {channel['Channel']}")
            st.caption(channel["Categories"] or "No topic label")
            metrics = st.columns(2)
            metrics[0].metric("Subscribers", f"{channel['Subscribers']:,}" if channel["Subscribers"] is not None else "Hidden")
            metrics[1].metric("Views/day", f"{channel['Views/day']:,}" if channel["Views/day"] is not None else "Collecting")
            st.link_button("Open channel", channel["URL"], width="stretch")
        else:
            st.info("A channel spotlight will appear after discovery.")

    bottom_left, bottom_right = st.columns([1, 1], gap="small")
    with bottom_left, st.container(border=True):
        st.subheader("Channel size distribution")
        subscribers = [row["Subscribers"] for row in data.channel_rows if row["Subscribers"] is not None]
        if subscribers:
            bands = pd.cut(
                pd.Series(subscribers),
                bins=[0, 10_000, 100_000, 1_000_000, 10_000_000, float("inf")],
                labels=["Under 10k", "10k-100k", "100k-1m", "1m-10m", "10m+"],
                include_lowest=True,
            ).value_counts(sort=False)
            st.bar_chart(bands, color="#528cff", height=190, width="stretch")
        else:
            st.info("Subscriber counts are unavailable for this sample.")
    with bottom_right, st.container(border=True):
        st.subheader("Videos driving attention")
        if data.video_rows:
            videos = pd.DataFrame(data.video_rows).sort_values("Views/day", ascending=False, na_position="last").head(5)
            st.dataframe(
                videos[["Thumbnail", "Video", "Channel", "Views/day", "URL"]],
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


def _render_page(page: str, data: DashboardData) -> None:
    """Render the selected detail view using precomputed business data."""
    if page == "Overview":
        _render_overview(data)
    elif page == "Trending channels":
        with st.container(border=True):
            st.subheader("Trending channel leaders")
            if data.channel_performance:
                st.dataframe(
                    pd.DataFrame(data.channel_performance)[["Thumbnail", "Channel", "Categories", "Subscribers", "Weekly subscribers", "Weekly growth %", "Views/day", "Engagement %", "URL"]],
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
            st.caption("Growth rates need observations on separate days and remain blank without that history.")
    elif page == "Category trends":
        with st.container(border=True):
            st.subheader("Category momentum")
            if data.category_rows:
                categories = pd.DataFrame(data.category_rows)
                metric = "Observed view gain" if categories["Observed view gain"].notna().any() else "Tracked videos"
                st.bar_chart(categories.set_index("Category")[[metric]], color="#41c7b2", height=350, width="stretch")
                st.dataframe(categories, width="stretch", hide_index=True)
                st.caption("Before repeat snapshots, this shows the discovered sample size, not category-wide YouTube popularity.")
            else:
                st.info("Category signals appear after discovery.")
    elif page == "Channel explorer":
        with st.container(border=True):
            st.subheader("Explore a channel")
            if data.channel_performance:
                choices = {
                    f"{row['Channel']} ({row['Channel ID'][-4:]})": row["Channel ID"]
                    for row in data.channel_performance
                }
                label = st.selectbox("Channel", list(choices))
                channel_id = choices[label]
                channel = next(row for row in data.channel_performance if row["Channel ID"] == channel_id)
                st.subheader(channel["Channel"])
                metrics = st.columns(4)
                metrics[0].metric("Subscribers", f"{channel['Subscribers']:,}" if channel["Subscribers"] is not None else "Hidden")
                metrics[1].metric("Weekly growth", f"{channel['Weekly growth %']:+.1f}%" if channel["Weekly growth %"] is not None else "Building history")
                metrics[2].metric("Views/day", f"{channel['Views/day']:,}" if channel["Views/day"] is not None else "Collecting")
                metrics[3].metric("Engagement", f"{channel['Engagement %']:.2f}%" if channel["Engagement %"] is not None else "Unavailable")
                st.caption(channel["Categories"])
                st.link_button("Open channel", channel["URL"])
                videos = [row for row in data.video_rows if row["Channel ID"] == channel_id]
                if videos:
                    st.dataframe(
                        pd.DataFrame(videos)[["Thumbnail", "Video", "Views", "Views/day", "Engagement %", "URL"]],
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "Thumbnail": st.column_config.ImageColumn("", width="small"),
                            "URL": st.column_config.LinkColumn("Video", display_text="Watch"),
                        },
                    )
            else:
                st.info("Run discovery to add channels to the explorer.")
    elif page == "Top videos":
        with st.container(border=True):
            st.subheader("Top videos by daily view velocity")
            if data.video_rows:
                videos = pd.DataFrame(data.video_rows).sort_values("Views/day", ascending=False, na_position="last")
                st.dataframe(
                    videos[["Thumbnail", "Video", "Channel", "Category", "Views", "Views/day", "Engagement %", "URL"]],
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Thumbnail": st.column_config.ImageColumn("", width="small"),
                        "Views/day": st.column_config.NumberColumn("Views/day", format="%d"),
                        "Engagement %": st.column_config.NumberColumn("Engagement %", format="%.2f%%"),
                        "URL": st.column_config.LinkColumn("Video", display_text="Watch"),
                    },
                )
                st.caption("Views/day uses observed gains when available; otherwise it estimates lifetime views divided by video age.")
            else:
                st.info("Run discovery to find recent videos.")
    elif page == "Insights":
        with st.container(border=True):
            st.subheader("Topics in high-velocity video titles")
            if data.topic_terms:
                maximum = max(count for _, count in data.topic_terms)
                cloud = "".join(
                    f'<span style="font-size:{0.85 + count / maximum:.2f}rem;color:{"#58d2c0" if index % 3 == 0 else "#e3ebf7" if index % 3 == 1 else "#76a9ff"};padding:0.25rem 0.6rem;display:inline-block">{term}</span>'
                    for index, (term, count) in enumerate(data.topic_terms)
                )
                st.markdown(f'<div style="line-height:2.2">{cloud}</div>', unsafe_allow_html=True)
                st.caption("Title keywords are clues to investigate, not proof of why a channel grew.")
            else:
                st.info("Topic signals appear after video discovery.")
        with st.container(border=True):
            st.subheader("Measurement notes")
            st.markdown(
                "- Discovery covers three fixed searches, not all YouTube channels.\n"
                "- Subscriber growth requires repeat daily snapshots; public counts may be rounded.\n"
                "- Engagement uses public likes and comments, not channel analytics.\n"
                "- Video-title topics are correlation clues, not causal explanations."
            )


def main() -> None:
    """Fetch business data over HTTP and render the Streamlit application."""
    st.set_page_config(
        page_title="YouTube Signals",
        page_icon="YT",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _render_styles()

    api_url = os.getenv("YOUTUBE_TRENDS_API_URL", "http://127.0.0.1:8000").strip()
    access_token = os.getenv("DASHBOARD_API_TOKEN", "").strip()
    if not access_token:
        st.error("Set DASHBOARD_API_TOKEN in the presentation environment to connect securely.")
        st.stop()
    api_client = BusinessApiClient(api_url, access_token)

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

    try:
        initial_data = api_client.get_dashboard()
    except BusinessApiError as error:
        st.error(f"Business API unavailable: {error}")
        st.stop()

    columns = st.columns([1.8, 0.8, 0.8, 0.8, 0.8], vertical_alignment="bottom")
    with columns[0]:
        st.markdown(
            '<div class="dashboard-title">YouTube Trending Channels</div><div class="dashboard-subtitle">Fast-growing creators and emerging trends in US technology, AI, and education</div>',
            unsafe_allow_html=True,
        )
    with columns[1]:
        st.markdown('<div class="filter-label">Market</div><div class="filter-value">United States</div>', unsafe_allow_html=True)
    with columns[2]:
        category = st.selectbox("Category", ["All categories", *initial_data.category_options])
    with columns[3]:
        st.markdown('<div class="filter-label">Discovery window</div><div class="filter-value">Past 7 days</div>', unsafe_allow_html=True)
    with columns[4]:
        if st.button("Discover", width="stretch", help="Search YouTube and save a new daily snapshot."):
            try:
                with st.spinner("Searching YouTube and saving today's metrics..."):
                    channel_count, video_count = api_client.discover()
                st.success(f"Saved {channel_count} channels and {video_count} candidate videos.")
                st.rerun()
            except BusinessApiError as error:
                st.error(str(error))

    selected_category = None if category == "All categories" else category
    if selected_category is None:
        data = initial_data
    else:
        try:
            data = api_client.get_dashboard(selected_category)
        except BusinessApiError as error:
            st.error(f"Business API unavailable: {error}")
            st.stop()
    growth = [row["Weekly growth %"] for row in data.channel_rows if row["Weekly growth %"] is not None]
    average_growth = sum(growth) / len(growth) if growth else None
    velocities = [row["Views/day"] for row in data.video_rows if row["Views/day"] is not None]
    average_velocity = sum(velocities) / len(velocities) if velocities else None
    emerging = sum(
        row["Subscribers"] is not None and row["Subscribers"] < 100_000
        for row in data.channel_rows
    )

    metrics = st.columns(4)
    metrics[0].metric("Trending channels", len(data.channel_rows))
    metrics[1].metric(
        "Avg. subscriber growth",
        f"{average_growth:+.1f}%" if average_growth is not None else "Building history",
        "7-day rate" if average_growth is not None else None,
    )
    metrics[2].metric("Avg. views per day", f"{average_velocity:,.0f}" if average_velocity is not None else "No video data")
    metrics[3].metric("Emerging creators", emerging, "under 100k subscribers")

    if data.channel_snapshots:
        latest_capture = max(row["captured_at"] for row in data.channel_snapshots)
        st.caption(
            f"Latest snapshot: {pd.Timestamp(latest_capture).strftime('%b %d, %Y')}  |  "
            "Engagement is likes plus comments divided by views on discovered videos."
        )
    if not data.channel_snapshots:
        st.info("No snapshots yet. Use Discover to start collecting channel and video metrics.")

    _render_page(page, data)


if __name__ == "__main__":
    main()