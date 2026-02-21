# CodeLens — Codebase Q&A with Proof

> Upload any codebase. Ask questions in plain English. Get answers with exact file paths, line numbers, and code snippets.

**Live demo**: [your-deployment-url]  
**GitHub**: [your-repo-url]

---

## Features

| Feature | Details |
|---|---|
| ZIP upload | Drag-and-drop or browse, up to 50 MB |
| GitHub ingestion | Paste any public repo URL |
| Semantic search | Google gemini-embedding-001 embeddings |
| Cited answers | Every answer includes file + line number |
| Code snippets | Collapsible, syntax-highlighted proof |
| Refactor suggestions | Optional per-question code review |
| Q&A history | Last 10 Q&As per session, searchable |
| Tags | Label and organise Q&As |
| Markdown export | Download full session as `.md` |
| Session restore | Reopen previous session on page reload |

---

## Quick Start

### Prerequisites
- Python 3.8–3.13
- Free Gemini API key: https://aistudio.google.com/app/apikey

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/yourusername/codelens.git
cd codelens

# 2. Create virtual environment
python -m venv venv

# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API key
# Windows:
copy .env.example .env
# Mac/Linux:
cp .env.example .env
# Then edit .env and add your GEMINI_API_KEY

# 5. Run
python run.py
```

Open http://localhost:8000

---

## How to Use

**Step 1 — Load a codebase**
- Click **Upload ZIP** and drop your project zip, OR
- Click **GitHub URL** and paste a public repo link (e.g. `https://github.com/pallets/flask`)
- Wait for indexing to complete (~5–30 seconds depending on size)

**Step 2 — Ask a question**
- Type any question in plain English
- Try the suggestion chips for inspiration
- Toggle "Suggest refactors" for code improvement tips
- Press **Ask →** or Ctrl+Enter

**Step 3 — Read the answer**
- The answer cites exact file paths and line numbers
- Expand the **Referenced Code** cards to see the actual snippets
- Add tags to organise your Q&As
- Click any history item to reload a previous answer

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | System health check |
| POST | `/api/upload` | Upload and index a ZIP file |
| POST | `/api/github` | Ingest a public GitHub repo |
| GET | `/api/sessions/{id}` | Get session metadata |
| POST | `/api/ask` | Ask a question |
| GET | `/api/history/{session_id}` | Get Q&A history |
| POST | `/api/search-history` | Search Q&A history |
| POST | `/api/tag` | Add tags to a Q&A |
| DELETE | `/api/history/{qa_id}` | Delete a Q&A |
| GET | `/api/export/{session_id}` | Export session as markdown |

---

## Tech Stack

| Component | Technology | Why |
|---|---|---|
| Backend | FastAPI + Python | Fast async API, great DX |
| LLM | Google Gemini 1.5 Flash | Free tier, 1M context window |
| Embeddings | Google gemini-embedding-001 | Free, no local ML needed, Python 3.13 compatible |
| Vector search | Numpy cosine similarity | Zero dependencies, good enough for demos |
| Database | SQLite | Zero config, file-based persistence |
| Frontend | Vanilla HTML/CSS/JS | No build step, fast load |

---

## Deployment (Render.com — Free)

1. Push to GitHub
2. Go to [render.com](https://render.com) → New Web Service → connect repo
3. Set:
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variable: `GEMINI_API_KEY=your_key`
5. Deploy

---

## Docker

```bash
# Copy and fill in your API key
cp .env.example .env

# Build and run
docker-compose up --build
```

---

## What's Done

- ✅ ZIP upload + extraction + indexing
- ✅ GitHub public repo ingestion
- ✅ Semantic Q&A with cited file paths and line numbers
- ✅ Code snippet viewer with syntax highlighting
- ✅ Optional refactor suggestions
- ✅ Session persistence (localStorage)
- ✅ Q&A history with search and tags
- ✅ Markdown export
- ✅ System status page
- ✅ Docker + docker-compose

## What's Not Done

- ❌ Private GitHub repos (would need OAuth)
- ❌ Streaming responses (would need SSE or WebSocket)
- ❌ Multi-user auth (single-user demo only)
- ❌ Persistent index storage across server restarts (indexes live in filesystem)

---

## Project Structure

```
codelens/
├── backend/
│   ├── __init__.py
│   ├── main.py           # FastAPI app, all endpoints
│   ├── indexer.py        # Code chunking + embedding + search
│   ├── qa_engine.py      # Gemini Q&A generation
│   ├── database.py       # SQLite session + history storage
│   └── github_fetcher.py # Public GitHub repo downloader
├── frontend/
│   ├── index.html        # Main application page
│   ├── status.html       # System health dashboard
│   └── static/
│       ├── css/app.css   # All styles
│       └── js/app.js     # All client-side logic
├── tests/
│   └── test_api.py       # Integration + unit tests
├── .env.example          # Environment template
├── requirements.txt      # Python dependencies
├── run.py                # Local dev entry point
├── Dockerfile            # Container build
└── docker-compose.yml    # Docker Compose config
```