"""Content-addressed disk cache helpers. Files live under ``settings.cache_dir/{kind}/``."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from ..config import get_settings


def key_of(*parts: Any) -> str:
    """sha1 hex of the parts; floats (incl. numpy floats) are rounded to 4 decimal places."""
    out: list[str] = []
    for p in parts:
        if isinstance(p, bool) or p is None:
            out.append(repr(p))
            continue
        if not isinstance(p, (str, bytes, int, float)) and hasattr(p, "item"):
            try:
                p = p.item()  # numpy scalar -> python scalar
            except Exception:
                pass
        if isinstance(p, float):
            out.append(f"{round(p, 4):.4f}")
        else:
            out.append(str(p))
    return hashlib.sha1("|".join(out).encode("utf-8")).hexdigest()


def cache_path(kind: str, key: str, ext: str) -> Path:
    """``cache_dir/{kind}/{key}.{ext}`` (parent directory is created)."""
    d = get_settings().cache_dir / kind
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.{ext.lstrip('.')}"


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` via tmp file + rename (never leaves a partial file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(kind: str, key: str, ttl_s: Optional[float]) -> Any | None:
    """Cached JSON, or None if missing / older than ``ttl_s`` (None = never expires) / unreadable."""
    p = cache_path(kind, key, "json")
    try:
        if ttl_s is not None and time.time() - p.stat().st_mtime > ttl_s:
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(kind: str, key: str, obj: Any) -> None:
    atomic_write_bytes(cache_path(kind, key, "json"), json.dumps(obj).encode("utf-8"))
