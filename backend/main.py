"""
main.py — FastAPI application for CodeLens: Codebase Q&A with Proof.

Production hardening:
  - Structured JSON logging (Python logging module, not bare print)
  - Per-IP rate limiting via slowapi
  - Asyncio semaphore — max 3 concurrent indexing jobs
  - UUID format validation on all session_id parameters
  - Zip-slip attack prevention on ZIP extraction
  - Request-ID header on every response for traceability
"""

import os
import re
import time
import uuid
import zipfile
import shutil
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel, field_validator

from .database       import Database
from .indexer        import CodebaseIndexer
from .qa_engine      import QAEngine
from .github_fetcher import GitHubFetcher

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("codelens")

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# ── Concurrency guard (max 3 simultaneous indexing jobs) ─────────────────────
INDEX_SEMAPHORE = asyncio.Semaphore(3)

# ── UUID validation helper ────────────────────────────────────────────────────
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

def validate_session_id(session_id: str) -> str:
    """Raise 400 if session_id is not a valid UUID."""
    if not UUID_RE.match(session_id.lower()):
        raise HTTPException(400, "Invalid session_id format.")
    return session_id.lower()

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="CodeLens — Codebase Q&A", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
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


# ── Request-ID + access log middleware ───────────────────────────────────────
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid      = str(uuid.uuid4())[:8]
    t0       = time.time()
    response = await call_next(request)
    ms       = round((time.time() - t0) * 1000, 1)
    response.headers["X-Request-ID"] = rid
    logger.info(
        '"method":"%s","path":"%s","status":%d,"ms":%s,"rid":"%s"',
        request.method, request.url.path, response.status_code, ms, rid,
    )
    return response


# ── Pydantic models ───────────────────────────────────────────────────────────
class QuestionRequest(BaseModel):
    session_id: str
    question: str
    generate_refactor: bool = False

    @field_validator("session_id")
    @classmethod
    def check_session_id(cls, v: str) -> str:
        if not UUID_RE.match(v.lower()):
            raise ValueError("session_id must be a valid UUID")
        return v.lower()

    @field_validator("question")
    @classmethod
    def check_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question cannot be empty")
        if len(v) > 2000:
            raise ValueError("question must be under 2000 characters")
        return v

class GithubRequest(BaseModel):
    repo_url: str

    @field_validator("repo_url")
    @classmethod
    def check_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("repo_url cannot be empty")
        if "github.com" not in v:
            raise ValueError("Only GitHub URLs are supported")
        return v

class TagRequest(BaseModel):
    qa_id: str
    tags: List[str]

    @field_validator("tags")
    @classmethod
    def check_tags(cls, v: List[str]) -> List[str]:
        if len(v) > 20:
            raise ValueError("Maximum 20 tags per Q&A")
        return [t.strip().lower()[:32] for t in v if t.strip()]

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
    t0      = time.time()
    backend = {"status": "ok", "message": "FastAPI is running"}

    try:
        db.ping()
        database = {"status": "ok", "message": "SQLite connected"}
    except Exception as e:
        logger.error('"event":"db_ping_failed","error":"%s"', e)
        database = {"status": "error", "message": str(e)}

    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        llm = {"status": "error", "message": "GEMINI_API_KEY not configured"}
    else:
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            next(iter(genai.list_models()), None)
            llm = {"status": "ok", "message": "Gemini connected (gemini-1.5-flash + gemini-embedding-001)"}
        except Exception as e:
            logger.error('"event":"gemini_ping_failed","error":"%s"', str(e)[:120])
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
@limiter.limit("10/minute")
async def upload_zip(request: Request, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No file provided.")
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "Only .zip files are accepted.")

    session_id  = str(uuid.uuid4())
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(parents=True)
    logger.info('"event":"upload_start","session":"%s","file":"%s"',
                session_id, file.filename)

    try:
        content = await file.read()
        if len(content) > 50 * 1024 * 1024:
            shutil.rmtree(str(session_dir))
            raise HTTPException(400, "ZIP exceeds 50 MB limit.")

        zip_path    = session_dir / "code.zip"
        extract_dir = session_dir / "source"
        zip_path.write_bytes(content)

        try:
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                # Zip-slip prevention: reject any member that escapes extract_dir
                resolved_root = extract_dir.resolve()
                for member in zf.namelist():
                    dest = (extract_dir / member).resolve()
                    if not str(dest).startswith(str(resolved_root)):
                        shutil.rmtree(str(session_dir))
                        raise HTTPException(400, "Invalid ZIP: path traversal detected.")
                zf.extractall(str(extract_dir))
        except zipfile.BadZipFile:
            shutil.rmtree(str(session_dir))
            raise HTTPException(400, "Invalid or corrupted ZIP file.")

        logger.info('"event":"extracted","session":"%s"', session_id)

        async with INDEX_SEMAPHORE:
            try:
                stats = await asyncio.to_thread(
                    indexer.index_directory, session_id, str(extract_dir)
                )
            except ValueError as e:
                shutil.rmtree(str(session_dir))
                raise HTTPException(400, str(e))
            except Exception:
                shutil.rmtree(str(session_dir))
                logger.exception('"event":"index_error","session":"%s"', session_id)
                raise HTTPException(500, "Indexing failed. Please try again.")

        db.create_session(session_id, file.filename, "zip", stats)
        logger.info('"event":"upload_complete","session":"%s","files":%d,"chunks":%d',
                    session_id, stats["files_indexed"], stats["total_chunks"])
        return {"session_id": session_id, "source": file.filename, "stats": stats}

    except HTTPException:
        raise
    except Exception:
        logger.exception('"event":"upload_unexpected","session":"%s"', session_id)
        if session_dir.exists():
            shutil.rmtree(str(session_dir))
        raise HTTPException(500, "Upload failed. Please try again.")


# ── GitHub ────────────────────────────────────────────────────────────────────
@app.post("/api/github")
@limiter.limit("5/minute")
async def ingest_github(request: Request, req: GithubRequest):
    session_id  = str(uuid.uuid4())
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(parents=True)
    logger.info('"event":"github_start","session":"%s","url":"%s"',
                session_id, req.repo_url)

    try:
        extract_dir = session_dir / "source"
        try:
            meta = await github_fetcher.fetch_and_extract(
                req.repo_url.strip(), str(extract_dir))
        except ValueError as e:
            shutil.rmtree(str(session_dir))
            raise HTTPException(400, str(e))
        except Exception:
            shutil.rmtree(str(session_dir))
            logger.exception('"event":"github_fetch_error","session":"%s"', session_id)
            raise HTTPException(500, "GitHub fetch failed. Is the repo public?")

        async with INDEX_SEMAPHORE:
            try:
                stats = await asyncio.to_thread(
                    indexer.index_directory, session_id, str(extract_dir)
                )
            except ValueError as e:
                shutil.rmtree(str(session_dir))
                raise HTTPException(400, str(e))
            except Exception:
                shutil.rmtree(str(session_dir))
                logger.exception('"event":"index_error","session":"%s"', session_id)
                raise HTTPException(500, "Indexing failed. Please try again.")

        stats.update(meta)
        db.create_session(session_id, req.repo_url.strip(), "github", stats)
        logger.info('"event":"github_complete","session":"%s","files":%d',
                    session_id, stats["files_indexed"])
        return {"session_id": session_id, "source": req.repo_url, "stats": stats}

    except HTTPException:
        raise
    except Exception:
        logger.exception('"event":"github_unexpected","session":"%s"', session_id)
        if session_dir.exists():
            shutil.rmtree(str(session_dir))
        raise HTTPException(500, "GitHub ingest failed. Please try again.")


# ── Session ───────────────────────────────────────────────────────────────────
@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    validate_session_id(session_id)
    s = db.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found.")
    return s


# ── Ask ───────────────────────────────────────────────────────────────────────
@app.post("/api/ask")
@limiter.limit("30/minute")
async def ask(request: Request, req: QuestionRequest):
    if not db.get_session(req.session_id):
        raise HTTPException(404, "Session not found. Please upload a codebase first.")
    if not indexer.has_index(req.session_id):
        raise HTTPException(400, "Index missing. Please re-upload the codebase.")

    logger.info('"event":"ask","session":"%s","q_len":%d',
                req.session_id, len(req.question))
    t0 = time.time()

    try:
        result = await asyncio.to_thread(
            qa_engine.answer, req.session_id, req.question, req.generate_refactor
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        logger.exception('"event":"ask_error","session":"%s"', req.session_id)
        raise HTTPException(500, "Q&A failed. Please try again.")

    ms = round((time.time() - t0) * 1000)
    logger.info('"event":"ask_complete","session":"%s","ms":%d', req.session_id, ms)
    result["qa_id"] = db.save_qa(req.session_id, req.question, result)
    return result


# ── History ───────────────────────────────────────────────────────────────────
@app.get("/api/history/{session_id}")
async def history(session_id: str, limit: int = 10):
    validate_session_id(session_id)
    return {"history": db.get_history(session_id, min(limit, 50))}

@app.post("/api/search-history")
async def search_history(req: SearchRequest):
    validate_session_id(req.session_id)
    if not req.query.strip():
        raise HTTPException(400, "Search query cannot be empty.")
    return {"results": db.search_history(req.session_id, req.query.strip()[:200])}

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
    validate_session_id(session_id)
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found.")

    records = db.get_history(session_id, 100)
    lines   = [
        "# Codebase Q&A Export", "",
        f"**Source**: `{session['source']}`",
        f"**Exported**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Total Q&As**: {len(records)}", "", "---", "",
    ]
    for i, rec in enumerate(records, 1):
        tags_str = ", ".join(f"`{t}`" for t in rec.get("tags", [])) or "_none_"
        lines += [
            f"## Q{i}: {rec['question']}", "",
            f"**Tags**: {tags_str}", "", "### Answer", "", rec["answer"], "",
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
        headers={"Content-Disposition":
                 f'attachment; filename="codebase_qa_{session_id[:8]}.md"'},
    )