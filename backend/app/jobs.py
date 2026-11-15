"""In-process job queue (1 worker) + simple per-IP token-bucket rate limiting."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import time
from collections import defaultdict

from . import db
from .models import ErrorInfo, Investigation, InvestigationRequest, Progress, RequestEcho, Target

log = logging.getLogger("astra.jobs")

_queue: "asyncio.Queue[tuple[str, InvestigationRequest]]" = asyncio.Queue()
_worker: asyncio.Task | None = None
_live: dict[str, Investigation] = {}  # in-memory latest state for running jobs


def request_key(req: InvestigationRequest) -> str:
    from .config import get_settings

    parts = (
        f"{round(req.ra, 4)}|{round(req.dec, 4)}|{req.fov_arcmin}|{sorted(req.detectors)}|"
        f"{req.max_exposures}|{req.propagate_pm}|{get_settings().spherex_collections}|{(req.name or '').lower()}"
    )
    return hashlib.sha1(parts.encode()).hexdigest()


def new_id() -> str:
    return "inv_" + secrets.token_hex(4)


def skeleton(inv_id: str, req: InvestigationRequest) -> Investigation:
    return Investigation(
        id=inv_id,
        status="queued",
        progress=Progress(stage="resolve", pct=0, message="Queued"),
        request=RequestEcho(ra=req.ra, dec=req.dec, fov_arcmin=req.fov_arcmin, name=req.name, detectors=req.detectors),
        target=Target(name=req.name, ra=req.ra, dec=req.dec, source="coordinates"),
        created_at=db.now_iso(),
    )


def _dump(inv: Investigation) -> str:
    return inv.model_dump_json(by_alias=True)


async def submit(req: InvestigationRequest) -> tuple[str, str]:
    key = request_key(req)
    row = db.find_by_key(key)
    if row is not None:
        return row["id"], row["status"]
    inv_id = new_id()
    inv = skeleton(inv_id, req)
    db.insert_investigation(inv_id, key, _dump(inv))
    _live[inv_id] = inv
    await _queue.put((inv_id, req))
    ensure_worker()
    return inv_id, "queued"


def get_live(inv_id: str) -> Investigation | None:
    return _live.get(inv_id)


async def _progress(inv: Investigation) -> None:
    _live[inv.id] = inv
    db.update_investigation(inv.id, inv.status, _dump(inv))


async def _run_one(inv_id: str, req: InvestigationRequest) -> None:
    from .pipeline import run_investigation

    try:
        inv = await run_investigation(inv_id, req, _progress)
        inv.status = "done"
        db.update_investigation(inv_id, "done", _dump(inv))
    except Exception as e:  # pipeline should raise PipelineError with a code; anything else is internal
        log.exception("investigation %s failed", inv_id)
        inv = _live.get(inv_id) or skeleton(inv_id, req)
        inv.status = "error"
        code = getattr(e, "code", "internal_error")
        msg = str(e) if getattr(e, "code", None) else "Internal error while processing this investigation."
        inv.error = ErrorInfo(code=code, message=msg)
        db.update_investigation(inv_id, "error", _dump(inv))
    finally:
        _live.pop(inv_id, None)


async def _worker_loop() -> None:
    while True:
        inv_id, req = await _queue.get()
        try:
            await _run_one(inv_id, req)
        finally:
            _queue.task_done()


def ensure_worker() -> None:
    global _worker
    if _worker is None or _worker.done():
        _worker = asyncio.get_running_loop().create_task(_worker_loop())


def queue_position(inv_id: str) -> int:
    return sum(1 for (i, _) in list(_queue._queue) if i != inv_id)  # type: ignore[attr-defined]


# ---------------- rate limiting ----------------
class RateLimiter:
    def __init__(self, per_minute: int):
        self.rate = per_minute / 60.0
        self.cap = float(per_minute)
        self.buckets: dict[str, tuple[float, float]] = defaultdict(lambda: (self.cap, time.monotonic()))

    def allow(self, key: str) -> bool:
        tokens, last = self.buckets[key]
        now = time.monotonic()
        tokens = min(self.cap, tokens + (now - last) * self.rate)
        if tokens < 1:
            self.buckets[key] = (tokens, now)
            return False
        self.buckets[key] = (tokens - 1, now)
        return True


inv_limiter = RateLimiter(6)
explain_limiter = RateLimiter(10)
annot_limiter = RateLimiter(20)
