"""Citizen-science annotations (sqlite3, stdlib). Notes and authors are stored and returned as plain text."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .models import Annotation, AnnotationIn, AnnotationList

VERDICTS = ("real", "artifact", "known", "unsure")


def init_annotations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS annotations ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT NOT NULL, verdict TEXT NOT NULL, "
        "note TEXT NOT NULL DEFAULT '', author TEXT, created_at TEXT NOT NULL)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_annotations_candidate ON annotations(candidate_id)")
    conn.commit()


def _row(r) -> Annotation:
    return Annotation(id=r[0], candidate_id=r[1], verdict=r[2], note=r[3] or "", author=r[4], created_at=r[5])


def insert_annotation(conn: sqlite3.Connection, cid: str, a: AnnotationIn) -> Annotation:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO annotations (candidate_id, verdict, note, author, created_at) VALUES (?, ?, ?, ?, ?)",
        (cid, a.verdict, a.note or "", a.author, now))
    conn.commit()
    return Annotation(id=int(cur.lastrowid), candidate_id=cid, verdict=a.verdict, note=a.note or "",
                      author=a.author, created_at=now)


def _empty_tally() -> dict[str, int]:
    return {v: 0 for v in VERDICTS}


def list_annotations(conn: sqlite3.Connection, cid: str) -> AnnotationList:
    rows = conn.execute(
        "SELECT id, candidate_id, verdict, note, author, created_at FROM annotations "
        "WHERE candidate_id = ? ORDER BY id", (cid,)).fetchall()
    anns = [_row(r) for r in rows]
    tally = _empty_tally()
    for a in anns:
        tally[a.verdict] = tally.get(a.verdict, 0) + 1
    return AnnotationList(candidate_id=cid, annotations=anns, tally=tally)


def tallies(conn: sqlite3.Connection, cids: list[str]) -> dict[str, dict[str, int]]:
    out = {c: _empty_tally() for c in cids}
    if not cids:
        return out
    for i in range(0, len(cids), 500):
        chunk = cids[i:i + 500]
        q = ",".join("?" * len(chunk))
        for cid, verdict, n in conn.execute(
                f"SELECT candidate_id, verdict, COUNT(*) FROM annotations WHERE candidate_id IN ({q}) "
                "GROUP BY candidate_id, verdict", chunk):
            out[cid][verdict] = int(n)
    return out
