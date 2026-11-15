"""SQLite persistence (stdlib sqlite3): investigations + explain cache. Annotations live in db_annotations.py."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from .config import get_settings

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        c = sqlite3.connect(get_settings().db_path, check_same_thread=False, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS investigations(
              id TEXT PRIMARY KEY, key TEXT, status TEXT, json TEXT, created_at TEXT, updated_at TEXT);
            CREATE INDEX IF NOT EXISTS ix_inv_key ON investigations(key);
            CREATE TABLE IF NOT EXISTS explain_cache(k TEXT PRIMARY KEY, json TEXT, created_at TEXT);
            """
        )
        from . import db_annotations

        db_annotations.init_annotations(c)
        _conn = c
    return _conn


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_by_key(key: str) -> Optional[sqlite3.Row]:
    with _lock:
        return conn().execute(
            "SELECT * FROM investigations WHERE key=? AND status!='error' ORDER BY created_at DESC LIMIT 1", (key,)
        ).fetchone()


def insert_investigation(inv_id: str, key: str, inv_json: str) -> None:
    t = now_iso()
    with _lock:
        conn().execute(
            "INSERT OR REPLACE INTO investigations(id,key,status,json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (inv_id, key, "queued", inv_json, t, t),
        )


def update_investigation(inv_id: str, status: str, inv_json: str) -> None:
    with _lock:
        conn().execute(
            "UPDATE investigations SET status=?, json=?, updated_at=? WHERE id=?", (status, inv_json, now_iso(), inv_id)
        )


def get_investigation_json(inv_id: str) -> Optional[str]:
    with _lock:
        r = conn().execute("SELECT json FROM investigations WHERE id=?", (inv_id,)).fetchone()
    return r["json"] if r else None


def list_investigations(limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        rows = conn().execute(
            "SELECT id, status, json, created_at FROM investigations ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        try:
            d = json.loads(r["json"])
        except Exception:
            continue
        req = d.get("request", {})
        ev = d.get("evidence") or {}
        out.append(
            {
                "id": r["id"], "status": r["status"], "name": req.get("name"), "ra": req.get("ra"),
                "dec": req.get("dec"), "fov_arcmin": req.get("fov_arcmin"), "created_at": r["created_at"],
                "classification": ev.get("classification") if r["status"] == "done" else None,
                "confidence": ev.get("confidence") if r["status"] == "done" else None,
            }
        )
    return out


def done_investigations(limit: int = 50) -> list[dict[str, Any]]:
    with _lock:
        rows = conn().execute(
            "SELECT json FROM investigations WHERE status='done' ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    res = []
    for r in rows:
        try:
            res.append(json.loads(r["json"]))
        except Exception:
            pass
    return res


def mark_stale_running() -> None:
    """On startup, jobs that were queued/running in a dead process are marked as error."""
    with _lock:
        rows = conn().execute("SELECT id, json FROM investigations WHERE status IN ('queued','running')").fetchall()
        for r in rows:
            try:
                d = json.loads(r["json"])
                d["status"] = "error"
                d["error"] = {"code": "interrupted", "message": "Server restarted before the job finished. Please retry."}
                conn().execute(
                    "UPDATE investigations SET status='error', json=? WHERE id=?", (json.dumps(d), r["id"])
                )
            except Exception:
                pass


def explain_get(k: str) -> Optional[str]:
    with _lock:
        r = conn().execute("SELECT json FROM explain_cache WHERE k=?", (k,)).fetchone()
    return r["json"] if r else None


def explain_put(k: str, j: str) -> None:
    with _lock:
        conn().execute("INSERT OR REPLACE INTO explain_cache(k,json,created_at) VALUES(?,?,?)", (k, j, now_iso()))


def annotations_conn() -> sqlite3.Connection:
    return conn()


def locked():
    return _lock
