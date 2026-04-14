# DashBoardAiFlow

Personal AI-powered knowledge dashboard that autonomously scouts cybersecurity and tech news, builds a 3D knowledge graph, and generates content drafts.

## Features

- **AI Scout Engine** — Crawls RSS feeds from 9 sources (BleepingComputer, The Hacker News, Fortinet, etc.) and scores articles by relevance
- **Knowledge Graph** — 3D force-directed graph visualizing relationships between articles, sources, and entities
- **Synapse Engine** — Uses Gemini AI to extract entities (companies, threats, CVEs) from articles and link them in the graph
- **Harvest Mode** — One-click LinkedIn post and Executive Brief generation from any Gold-tier article
- **Discord Alerts** — Real-time notifications when a high-value article is detected
- **Obsidian Integration** — Auto-exports key articles as Markdown notes

## Setup

```bash
pip install feedparser streamlit pandas google-genai plotly requests
```

Copy `config.example.py` and set your keys:
```python
GEMINI_API_KEY = "your-key-here"
DISCORD_WEBHOOK_URL = "your-webhook-url"  # optional
```

## Run

```bash
# Option 1: Double-click run_system.bat (Windows)

# Option 2: Manual
python ai_scout.py          # background news farming bot
streamlit run dashboard.py  # web dashboard
```

## Stack

- Python 3.11+
- Streamlit
- SQLite
- Google Gemini API (gemini-2.5-flash-lite)
- 3d-force-graph (WebGL via CDN)
- Plotly
