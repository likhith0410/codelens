"""database.py — SQLite persistence for sessions and Q&A history."""

import sqlite3
import uuid
import json
from datetime import datetime
from typing import Optional, List, Dict


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id          TEXT PRIMARY KEY,
                    source      TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    stats       TEXT NOT NULL,
                    created_at  TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qa_history (
                    id          TEXT PRIMARY KEY,
                    session_id  TEXT NOT NULL,
                    question    TEXT NOT NULL,
                    answer      TEXT NOT NULL,
                    snippets    TEXT NOT NULL,
                    tags        TEXT NOT NULL DEFAULT '[]',
                    created_at  TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );
                CREATE INDEX IF NOT EXISTS idx_qa_session
                    ON qa_history(session_id, created_at DESC);
            """)

    def ping(self):
        with self._conn() as conn:
            conn.execute("SELECT 1")

    def create_session(self, session_id: str, source: str, source_type: str, stats: dict):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?)",
                (session_id, source, source_type,
                 json.dumps(stats), datetime.utcnow().isoformat())
            )

    def get_session(self, session_id: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["stats"] = json.loads(d["stats"])
        return d

    def save_qa(self, session_id: str, question: str, result: dict) -> str:
        qa_id = str(uuid.uuid4())
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO qa_history VALUES (?,?,?,?,?,?,?)",
                (qa_id, session_id, question,
                 result.get("answer", ""),
                 json.dumps(result.get("snippets", [])),
                 "[]",
                 datetime.utcnow().isoformat())
            )
            conn.execute("""
                DELETE FROM qa_history
                WHERE session_id=?
                  AND id NOT IN (
                    SELECT id FROM qa_history
                    WHERE session_id=?
                    ORDER BY created_at DESC LIMIT 10
                  )
            """, (session_id, session_id))
        return qa_id

    def get_history(self, session_id: str, limit: int = 10) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM qa_history WHERE session_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (session_id, limit)
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["snippets"] = json.loads(d["snippets"])
            d["tags"]     = json.loads(d["tags"])
            result.append(d)
        return result

    def update_tags(self, qa_id: str, tags: List[str]):
        with self._conn() as conn:
            conn.execute(
                "UPDATE qa_history SET tags=? WHERE id=?",
                (json.dumps(tags), qa_id)
            )

    def delete_qa(self, qa_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM qa_history WHERE id=?", (qa_id,))

    def search_history(self, session_id: str, query: str) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM qa_history WHERE session_id=? "
                "AND (question LIKE ? OR answer LIKE ?) "
                "ORDER BY created_at DESC",
                (session_id, f"%{query}%", f"%{query}%")
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["snippets"] = json.loads(d["snippets"])
            d["tags"]     = json.loads(d["tags"])
            result.append(d)
        return result