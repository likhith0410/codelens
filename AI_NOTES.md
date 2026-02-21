#  How AI Was Used in This Project

## LLM & Embedding Provider

**LLM**: Google Gemini 1.5 Flash via `google-generativeai` SDK  
**Embeddings**: Google `gemini-embedding-001` via same SDK

**Why this stack?**
- **100% free** — both Gemini 1.5 Flash and gemini-embedding-001 are on the free tier (1500 req/day)
- **No local ML libraries** — sentence-transformers requires PyTorch (no Python 3.13 support); fastembed caps at Python 3.12. Google's API needs only the lightweight `google-generativeai` package — no C compiler, no DLL issues
- **Works on Python 3.13 Windows** — pure HTTPS calls under the hood
- **gemini-embedding-001** is Google's retrieval embedding model, confirmed available via `list_models()`

**Vector search**: Pure numpy cosine similarity — no FAISS needed. Simple, zero extra dependencies, fast enough for codebases up to ~10,000 chunks.

---

## What AI Was Used For

### 1. Architecture Decisions
Researched trade-offs between local embeddings (sentence-transformers, fastembed) vs API-based embeddings. After running into Python 3.13 compatibility walls with all local ML libraries, settled on Google's embedding API — same semantic quality, zero local dependencies.

### 2. Chunking Strategy
Researched best practices for chunking code files for semantic search. Settled on fixed 60-line chunks with 10-line overlap, each prefixed with the file path and line numbers — so the LLM always knows the provenance of each chunk.

### 3. Prompt Engineering
Iterated on the Q&A system prompt. Key constraints: "use ONLY the provided snippets", "do NOT invent file paths", format references as `filename.py (lines X–Y)`. This prevents hallucination and grounds every answer in real code.

### 4. Frontend UX
Used AI assistance to design the step-by-step UI flow, collapsible snippet cards, suggestion chips, and session persistence.

### 5. Debugging
Used AI assistance to trace the Python 3.13 + PyTorch DLL crash, the WatchFiles reload-during-upload issue on Windows, and the Google API model name (`text-embedding-004` is not supported in SDK v0.7.x — correct name is `gemini-embedding-001`, confirmed via `list_models()`).

---

## What Was Verified Manually

- **All backend modules** — understood every function in indexer, qa_engine, database, github_fetcher, main
- **The cosine similarity math** — verified `(embeddings @ query_vec.T).flatten()` gives correct ranking
- **SQLite schema** — designed and tested sessions + qa_history tables; verified the DELETE-keep-last-10 subquery works correctly
- **API model name** — ran `genai.list_models()` live to confirm `models/gemini-embedding-001` is the correct identifier
- **Windows path separators** — tested that `.replace("\\", "/")` correctly normalises chunk file paths on Windows
- **Google free tier limits** — confirmed 1500 requests/day covers both Q&A and embedding calls for a typical demo workload