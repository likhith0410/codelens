"""main.py — FastAPI application for CodeLens: Codebase Q&A with Proof."""

import os
import time
import uuid
import zipfile
import shutil
import traceback
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .database      import Database
from .indexer       import CodebaseIndexer
from .qa_engine     import QAEngine
from .github_fetcher import GitHubFetcher

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="CodeLens — Codebase Q&A", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

BASE_DIR     = Path(__file__).parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR   = BASE_DIR / "uploads"
INDEX_DIR    = BASE_DIR / "indexes"

UPLOAD_DIR.mkdir(exist_ok=True)
INDEX_DIR.mkdir(exist_ok=True)

db             = Database(str(BASE_DIR / "qa_history.db"))
indexer        = CodebaseIndexer(str(INDEX_DIR))
qa_engine      = QAEngine(indexer)
github_fetcher = GitHubFetcher()


# ── Models ────────────────────────────────────────────────────────────────────
class QuestionRequest(BaseModel):
    session_id: str
    question: str
    generate_refactor: bool = False

class GithubRequest(BaseModel):
    repo_url: str

class TagRequest(BaseModel):
    qa_id: str
    tags: List[str]

class SearchRequest(BaseModel):
    session_id: str
    query: str


# ── Static ────────────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")

@app.get("/")
async def root():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/status")
async def status_page():
    return FileResponse(str(FRONTEND_DIR / "status.html"))


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    t0 = time.time()
    backend = {"status": "ok", "message": "FastAPI is running"}

    try:
        db.ping()
        database = {"status": "ok", "message": "SQLite connected"}
    except Exception as e:
        database = {"status": "error", "message": str(e)}

    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        llm = {"status": "error", "message": "GEMINI_API_KEY not configured"}
    else:
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            next(iter(genai.list_models()), None)
            llm = {"status": "ok", "message": "Gemini connected (gemini-1.5-flash)"}
        except Exception as e:
            llm = {"status": "error", "message": str(e)[:120]}

    overall = "ok" if all(
        s["status"] == "ok" for s in [backend, database, llm]
    ) else "degraded"

    return {
        "status":     overall,
        "latency_ms": round((time.time() - t0) * 1000, 1),
        "timestamp":  datetime.utcnow().isoformat() + "Z",
        "services":   {"backend": backend, "database": database, "llm": llm},
    }


# ── Upload ZIP ────────────────────────────────────────────────────────────────
@app.post("/api/upload")
async def upload_zip(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No file provided.")
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "Only .zip files are accepted.")

    session_id  = str(uuid.uuid4())
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(parents=True)

    try:
        content = await file.read()
        if len(content) > 50 * 1024 * 1024:
            shutil.rmtree(str(session_dir))
            raise HTTPException(400, "ZIP exceeds 50 MB limit.")

        zip_path = session_dir / "code.zip"
        zip_path.write_bytes(content)

        extract_dir = session_dir / "source"
        try:
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                zf.extractall(str(extract_dir))
        except zipfile.BadZipFile:
            shutil.rmtree(str(session_dir))
            raise HTTPException(400, "Invalid or corrupted ZIP file.")

        print(f"[CodeLens] Extracted to {extract_dir}")

        try:
            stats = indexer.index_directory(session_id, str(extract_dir))
        except ValueError as e:
            shutil.rmtree(str(session_dir))
            raise HTTPException(400, str(e))
        except Exception as e:
            shutil.rmtree(str(session_dir))
            print(f"[CodeLens] Indexing error:\n{traceback.format_exc()}")
            raise HTTPException(500, f"Indexing failed: {str(e)}")

        db.create_session(session_id, file.filename, "zip", stats)
        print(f"[CodeLens] Ready: {session_id} | {stats}")
        return {"session_id": session_id, "source": file.filename, "stats": stats}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CodeLens] Upload error:\n{traceback.format_exc()}")
        if session_dir.exists():
            shutil.rmtree(str(session_dir))
        raise HTTPException(500, f"Upload failed: {str(e)}")


# ── GitHub ────────────────────────────────────────────────────────────────────
@app.post("/api/github")
async def ingest_github(req: GithubRequest):
    if not req.repo_url.strip():
        raise HTTPException(400, "repo_url is required.")

    session_id  = str(uuid.uuid4())
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(parents=True)

    try:
        extract_dir = session_dir / "source"
        try:
            meta = await github_fetcher.fetch_and_extract(
                req.repo_url.strip(), str(extract_dir))
        except ValueError as e:
            shutil.rmtree(str(session_dir))
            raise HTTPException(400, str(e))
        except Exception as e:
            shutil.rmtree(str(session_dir))
            raise HTTPException(500, f"GitHub fetch failed: {str(e)}")

        try:
            stats = indexer.index_directory(session_id, str(extract_dir))
        except ValueError as e:
            shutil.rmtree(str(session_dir))
            raise HTTPException(400, str(e))
        except Exception as e:
            shutil.rmtree(str(session_dir))
            print(f"[CodeLens] Indexing error:\n{traceback.format_exc()}")
            raise HTTPException(500, f"Indexing failed: {str(e)}")

        stats.update(meta)
        db.create_session(session_id, req.repo_url.strip(), "github", stats)
        return {"session_id": session_id, "source": req.repo_url, "stats": stats}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CodeLens] GitHub error:\n{traceback.format_exc()}")
        if session_dir.exists():
            shutil.rmtree(str(session_dir))
        raise HTTPException(500, f"GitHub ingest failed: {str(e)}")


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    s = db.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found.")
    return s


# ── Ask ───────────────────────────────────────────────────────────────────────
@app.post("/api/ask")
async def ask(req: QuestionRequest):
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty.")
    if not db.get_session(req.session_id):
        raise HTTPException(404, "Session not found. Please upload a codebase first.")
    if not indexer.has_index(req.session_id):
        raise HTTPException(400, "Index missing. Please re-upload the codebase.")

    try:
        result = qa_engine.answer(
            req.session_id, req.question.strip(), req.generate_refactor)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        print(f"[CodeLens] Q&A error:\n{traceback.format_exc()}")
        raise HTTPException(500, f"Q&A failed: {str(e)}")

    result["qa_id"] = db.save_qa(req.session_id, req.question.strip(), result)
    return result


# ── History ───────────────────────────────────────────────────────────────────
@app.get("/api/history/{session_id}")
async def history(session_id: str, limit: int = 10):
    return {"history": db.get_history(session_id, limit)}

@app.post("/api/search-history")
async def search_history(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(400, "Search query cannot be empty.")
    return {"results": db.search_history(req.session_id, req.query.strip())}

@app.post("/api/tag")
async def tag_qa(req: TagRequest):
    db.update_tags(req.qa_id, req.tags)
    return {"status": "ok"}

@app.delete("/api/history/{qa_id}")
async def delete_qa(qa_id: str):
    db.delete_qa(qa_id)
    return {"status": "deleted"}


# ── Export ────────────────────────────────────────────────────────────────────
@app.get("/api/export/{session_id}")
async def export_session(session_id: str):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found.")

    records = db.get_history(session_id, 100)
    lines = [
        "# Codebase Q&A Export", "",
        f"**Source**: `{session['source']}`",
        f"**Exported**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Total Q&As**: {len(records)}", "", "---", "",
    ]
    for i, rec in enumerate(records, 1):
        tags_str = ", ".join(f"`{t}`" for t in rec.get("tags", [])) or "_none_"
        lines += [
            f"## Q{i}: {rec['question']}", "",
            f"**Tags**: {tags_str}", "",
            "### Answer", "", rec["answer"], "",
        ]
        for s in rec.get("snippets", [])[:3]:
            lines += [
                f"**`{s['file']}` (lines {s['line_start']}–{s['line_end']})**",
                f"```{s.get('language', '')}",
                s["raw"][:600] + ("..." if len(s["raw"]) > 600 else ""),
                "```", "",
            ]
        lines += ["---", ""]

    return Response(
        content="\n".join(lines),
        media_type="text/markdown",
        headers={
            "Content-Disposition":
                f'attachment; filename="codebase_qa_{session_id[:8]}.md"'
        },
    )