# YouTube Signals

A local dashboard for discovering US-English technology, AI, and education channels and tracking their public metrics over time.

## Setup

1. Install dependencies in the project virtual environment:

	```powershell
	.\venv\Scripts\python.exe -m pip install -r requirements.txt
	```

2. Create a YouTube Data API v3 key in Google Cloud and set it for the current PowerShell session:

	```powershell
	$env:YOUTUBE_API_KEY = "your-api-key"
	```

3. Start the dashboard:

	```powershell
	.\venv\Scripts\python.exe -m streamlit run .\video_stats.py
	```

Use **Discover and snapshot** once per day to collect comparable history. The dashboard stores snapshots locally in `youtube_trends.sqlite3`; it does not send collected data anywhere else.

## What the first version measures

- Discovery searches recent, popular videos for three fixed topics: technology, artificial intelligence, and education. Search results are a candidate sample, not a complete list of trending YouTube channels.
- Channel growth is calculated from saved subscriber-count snapshots. YouTube may round public subscriber counts, and growth rankings need snapshots on separate days.
- Category momentum sums observed view increases for discovered videos. It describes only the videos in this dashboard's tracked sample.
- Video engagement is estimated as public likes plus comments divided by views. It is not a channel-wide audience engagement rate.
- Video views per day uses observed view increases after repeat snapshots; until then it estimates lifetime views divided by video age.

Each discovery run uses three YouTube Search API requests plus batched video and channel lookups. Search requests consume quota, so the UI displays a rough estimate of 300 units per run; actual usage can vary with API configuration and requests.
