#  Key Prompts Used During Development

This file documents the major prompts used during the development of CodeLens,
in the order they were used.

---

## 1. Initial Architecture

> "I need to build a codebase Q&A tool with proof citations in 48 hours.
> The user uploads a ZIP or GitHub URL, asks a question in plain English,
> and gets an answer with exact file paths and line numbers.
> I can't use paid LLMs. What architecture would you recommend?"

**Output**: Settled on FastAPI + Google Gemini (free tier) + semantic embeddings + FAISS.
Later pivoted away from FAISS due to Python 3.13 compatibility issues.

---

## 2. Chunking Strategy

> "What's the best chunking strategy for indexing code files for semantic search?
> I need to preserve enough context for the LLM to understand the code,
> but chunks can't be too large or too small."

**Output**: 60-line chunks with 10-line overlap. Each chunk prefixed with
`# File: path/to/file.py (lines X-Y)` so the LLM has provenance context.

---

## 3. Embedding Library Selection

> "I need a free embedding library that works on Python 3.13 Windows.
> sentence-transformers requires PyTorch which doesn't support Python 3.13 yet.
> What are my options?"

**Output**: Identified that fastembed also caps at Python 3.12.
Final decision: use Google's `gemini-embedding-001` API — free tier,
no local dependencies, works on any Python version.

---

## 4. FastAPI Project Structure

> "Design a clean FastAPI project structure for a codebase Q&A API.
> It needs endpoints for: upload ZIP, ingest GitHub URL, ask question,
> get history, tag Q&As, search history, export session."

**Output**: 5-module backend (main, database, indexer, qa_engine, github_fetcher)
with 13 REST endpoints.

---

## 5. Q&A Prompt Design

> "Write a system prompt for a code Q&A assistant that:
> 1. Only uses the provided code snippets as context
> 2. Always cites specific file paths and line numbers
> 3. Never invents code that isn't in the snippets
> 4. Formats output in markdown"

**Output**: The prompt in `qa_engine.py` with the explicit constraints
"use ONLY the provided snippets" and "do NOT invent file paths".

---

## 6. SQLite Schema

> "Design a SQLite schema for storing codebase Q&A sessions.
> Need to store: session metadata, Q&A pairs with code snippets,
> tags, and keep only last 10 Q&As per session."

**Output**: Two-table schema (sessions + qa_history) with the
DELETE-keep-last-10 subquery pattern.

---

## 7. GitHub Repo Fetcher

> "Write an async function that downloads a public GitHub repo as a ZIP
> using the GitHub API, with size limits and error handling."

**Output**: `github_fetcher.py` using httpx async client with
the `/repos/{owner}/{repo}/zipball/{branch}` endpoint.

---

## 8. Frontend UX Design

> "Design a dark-themed UI for a codebase Q&A tool.
> It should feel premium, not generic Bootstrap.
> Three-step flow: load codebase → ask question → get answer with citations."

**Output**: Dark editorial theme with Syne + JetBrains Mono fonts,
animated terminal hero widget, collapsible snippet cards,
session persistence via localStorage.

---

## 9. Debugging: WatchFiles Reload Issue

> "Uvicorn's reload mode is killing my server mid-upload on Windows
> because WatchFiles sees new files being extracted to the uploads/ folder.
> How do I fix this?"

**Output**: Set `reload=False` in `uvicorn.run()` — reload is not needed
for a demo, and it was causing the subprocess to restart during file extraction.

---

## 10. Debugging: Google Embedding Model Name

> "I'm getting 404 errors from the Google Gemini embedding API.
> I tried 'models/text-embedding-004' and 'models/embedding-001' — both fail.
> How do I find the correct model name for my API key?"

**Output**: Run `genai.list_models()` to list available models.
Discovered the correct name is `models/gemini-embedding-001`.

---

## 11. Dropzone Bug Fix

> "My file upload dropzone isn't opening the file picker on click.
> I have a <label for='file-input'> inside the dropzone div,
> and I also have zone.addEventListener('click', () => input.click()).
> On some browsers this causes the file dialog to open and immediately close."

**Output**: Identified double-trigger bug — label click and zone click both
call `input.click()`, cancelling each other. Fix: remove the `<label>`,
use a plain `<span>` with `onclick="document.getElementById('file-input').click()"`.

---

## 12. Python 3.13 Compatibility

> "PyTorch doesn't support Python 3.13 yet. What embedding options are
> completely free and work on Python 3.13 Windows without any C compiler?"

**Output**: All local ML libraries (sentence-transformers, fastembed, onnxruntime-based)
have Python 3.12 caps or need compilation. Only viable option: use a cloud
embedding API. Chose Google's since we already use Gemini for Q&A.

---

## 13. Deployment Setup

> "Write a Dockerfile and docker-compose.yml for deploying this FastAPI app.
> It should work on Render.com free tier. No GPU needed."

**Output**: Multi-stage Dockerfile with non-root user, healthcheck,
and docker-compose with volume mounts for uploads/indexes.