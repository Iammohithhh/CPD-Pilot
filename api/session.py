"""
session.py — SQLite-backed session store.

Each session tracks:
  - session_id (UUID)
  - project_name (optional label)
  - current_stage (1–5)
  - stage_data: JSON dict keyed by stage number, each containing:
      artifact   — the structured output from that stage
      summary    — plain-English summary shown to the user
      approved   — bool: has the user approved this stage?
      feedback   — last refinement feedback (if any)
  - created_at / updated_at timestamps
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path(__file__).parent.parent / "outputs" / "sessions.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id   TEXT PRIMARY KEY,
            project_name TEXT NOT NULL DEFAULT '',
            current_stage INTEGER NOT NULL DEFAULT 1,
            stage_data   TEXT NOT NULL DEFAULT '{}',
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        )
    """)
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Public API ─────────────────────────────────────────────────────────────────

def create_session(project_name: str = "") -> dict:
    """Create a new session and return its full state dict."""
    session_id = str(uuid.uuid4())
    now = _now()
    with _connect() as conn:
        _init_db(conn)
        conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, project_name, 1, "{}", now, now),
        )
    return get_session(session_id)


def get_session(session_id: str) -> dict | None:
    """Return full session state or None if not found."""
    with _connect() as conn:
        _init_db(conn)
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    if row is None:
        return None
    return {
        "session_id": row["session_id"],
        "project_name": row["project_name"],
        "current_stage": row["current_stage"],
        "stage_data": json.loads(row["stage_data"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def update_stage(
    session_id: str,
    stage: int,
    artifact: Any,
    summary: str,
    approved: bool = False,
    feedback: str = "",
) -> dict:
    """Upsert stage data for a session. Returns updated session state."""
    sess = get_session(session_id)
    if sess is None:
        raise KeyError(f"Session {session_id!r} not found")

    stage_data = sess["stage_data"]
    stage_data[str(stage)] = {
        "artifact": artifact,
        "summary": summary,
        "approved": approved,
        "feedback": feedback,
    }
    # Advance current_stage pointer only when approving
    current = sess["current_stage"]
    if approved and stage == current and stage < 5:
        current = stage + 1

    with _connect() as conn:
        conn.execute(
            "UPDATE sessions SET stage_data=?, current_stage=?, updated_at=? "
            "WHERE session_id=?",
            (json.dumps(stage_data), current, _now(), session_id),
        )
    return get_session(session_id)


def approve_stage(session_id: str, stage: int) -> dict:
    """Mark a stage as approved and advance current_stage pointer."""
    sess = get_session(session_id)
    if sess is None:
        raise KeyError(f"Session {session_id!r} not found")
    existing = sess["stage_data"].get(str(stage), {})
    return update_stage(
        session_id,
        stage,
        artifact=existing.get("artifact"),
        summary=existing.get("summary", ""),
        approved=True,
        feedback=existing.get("feedback", ""),
    )


def set_feedback(session_id: str, stage: int, feedback: str) -> dict:
    """Store user refinement feedback without changing approval state."""
    sess = get_session(session_id)
    if sess is None:
        raise KeyError(f"Session {session_id!r} not found")
    existing = sess["stage_data"].get(str(stage), {})
    return update_stage(
        session_id,
        stage,
        artifact=existing.get("artifact"),
        summary=existing.get("summary", ""),
        approved=False,
        feedback=feedback,
    )


def list_sessions() -> list[dict]:
    """Return all sessions (id + name + current_stage + timestamps)."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            "SELECT session_id, project_name, current_stage, created_at, updated_at "
            "FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_session(session_id: str) -> bool:
    """Delete a session. Returns True if a row was deleted."""
    with _connect() as conn:
        _init_db(conn)
        cur = conn.execute(
            "DELETE FROM sessions WHERE session_id=?", (session_id,)
        )
    return cur.rowcount > 0
