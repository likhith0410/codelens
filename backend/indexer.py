"""
indexer.py — Indexes a codebase using Google gemini-embedding-001.

Model confirmed via list_models(): models/gemini-embedding-001
Supports embedContent — works with google-generativeai 0.7.2.
No local ML libraries — runs on Python 3.13 Windows.
"""

import os
import pickle
import time
from pathlib import Path
from typing import Dict, List, Any

import numpy as np
import google.generativeai as genai

# ── Config ────────────────────────────────────────────────────────────────────
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb", ".rs",
    ".cpp", ".c", ".h", ".hpp", ".cs", ".php", ".swift", ".kt", ".scala",
    ".sh", ".bash", ".zsh", ".yml", ".yaml", ".toml", ".json",
    ".md", ".txt", ".sql", ".html", ".css", ".scss", ".vue", ".svelte",
    ".graphql", ".proto",
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
    ".mypy_cache", ".eggs",
}

MAX_FILE_SIZE_KB = 300
CHUNK_SIZE       = 60
CHUNK_OVERLAP    = 10
EMBED_MODEL      = "models/gemini-embedding-001"
EMBED_BATCH_SIZE = 20


def _configure():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set.")
    genai.configure(api_key=api_key)


def _embed_texts(texts: List[str]) -> np.ndarray:
    """Embed a list of texts in batches. Returns L2-normalised array."""
    _configure()
    all_embeddings = []

    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i: i + EMBED_BATCH_SIZE]
        print(f"[CodeLens] Embedding batch {i // EMBED_BATCH_SIZE + 1} "
              f"({len(batch)} chunks)...")

        result = genai.embed_content(
            model=EMBED_MODEL,
            content=batch,
            task_type="retrieval_document",
        )
        all_embeddings.extend(result["embedding"])

        if i + EMBED_BATCH_SIZE < len(texts):
            time.sleep(0.3)

    arr = np.array(all_embeddings, dtype="float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-10
    return arr / norms


def _embed_query(query: str) -> np.ndarray:
    """Embed a single query. Returns L2-normalised row vector."""
    _configure()
    result = genai.embed_content(
        model=EMBED_MODEL,
        content=query,
        task_type="retrieval_query",
    )
    vec = np.array(result["embedding"], dtype="float32").reshape(1, -1)
    vec /= np.linalg.norm(vec) + 1e-10
    return vec


class CodebaseIndexer:
    def __init__(self, index_dir: str):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)

    def has_index(self, session_id: str) -> bool:
        return (self.index_dir / session_id / "embeddings.npy").exists()

    def index_directory(self, session_id: str, source_dir: str) -> Dict[str, Any]:
        session_idx_dir = self.index_dir / session_id
        session_idx_dir.mkdir(parents=True, exist_ok=True)

        chunks: List[Dict] = []
        files_indexed = 0
        files_skipped = 0
        source_path   = Path(source_dir)

        for filepath in source_path.rglob("*"):
            if not filepath.is_file():
                continue

            relative  = filepath.relative_to(source_path)
            parts_set = set(relative.parts[:-1])
            if parts_set & SKIP_DIRS:
                continue
            if any(p.startswith(".") for p in relative.parts[:-1]):
                continue

            try:
                size_kb = filepath.stat().st_size / 1024
            except OSError:
                files_skipped += 1
                continue

            if size_kb > MAX_FILE_SIZE_KB:
                files_skipped += 1
                continue

            ext        = filepath.suffix.lower()
            name_lower = filepath.name.lower()
            allowed    = {"dockerfile", "makefile", "rakefile",
                          "procfile", "gemfile", "pipfile", "requirements.txt"}
            if ext not in CODE_EXTENSIONS and name_lower not in allowed:
                files_skipped += 1
                continue

            try:
                text = filepath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                files_skipped += 1
                continue

            rel_str = str(relative).replace("\\", "/")
            chunks.extend(self._chunk_file(rel_str, text))
            files_indexed += 1

        if not chunks:
            raise ValueError(
                "No indexable source files found. "
                "Make sure the ZIP contains code files (.py, .js, .ts, etc.)"
            )

        print(f"[CodeLens] Indexing {len(chunks)} chunks from "
              f"{files_indexed} files via {EMBED_MODEL}...")

        embeddings = _embed_texts([c["text"] for c in chunks])

        np.save(str(session_idx_dir / "embeddings.npy"), embeddings)
        with open(session_idx_dir / "chunks.pkl", "wb") as f:
            pickle.dump(chunks, f)

        print(f"[CodeLens] Index saved. shape={embeddings.shape}")

        return {
            "files_indexed": files_indexed,
            "files_skipped": files_skipped,
            "total_chunks":  len(chunks),
        }

    def search(self, session_id: str, query: str, top_k: int = 8) -> List[Dict]:
        session_idx_dir = self.index_dir / session_id
        if not (session_idx_dir / "embeddings.npy").exists():
            raise ValueError("Index not found for this session.")

        embeddings = np.load(str(session_idx_dir / "embeddings.npy"))
        with open(session_idx_dir / "chunks.pkl", "rb") as f:
            chunks = pickle.load(f)

        query_vec   = _embed_query(query)
        scores      = (embeddings @ query_vec.T).flatten()
        k           = min(top_k, len(chunks))
        top_indices = np.argsort(scores)[::-1][:k]

        return [
            {**chunks[i], "score": float(scores[i])}
            for i in top_indices
        ]

    def _chunk_file(self, relative_path: str, content: str) -> List[Dict]:
        lines = content.splitlines()
        total = len(lines)
        if total == 0:
            return []

        chunks = []
        start  = 0
        while start < total:
            end = min(start + CHUNK_SIZE, total)
            raw = "\n".join(lines[start:end])
            if raw.strip():
                chunks.append({
                    "file":       relative_path,
                    "line_start": start + 1,
                    "line_end":   end,
                    "text":       f"# File: {relative_path} (lines {start+1}-{end})\n{raw}",
                    "raw":        raw,
                })
            if end == total:
                break
            start += CHUNK_SIZE - CHUNK_OVERLAP

        return chunks