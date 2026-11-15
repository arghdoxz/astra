"""Shared, SSRF-guarded httpx client (ARCHITECTURE section 8).

* one ``httpx.AsyncClient`` per running event loop (re-created if the loop changes, e.g. between pytest tests)
* ``User-Agent`` from ``config.USER_AGENT``; redirects followed
* host allow-list checked on the initial URL AND on every redirect hop (request event hook)
* retries on 502/503/504 and connect/read timeouts, backoff 1 / 3 / 9 s
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional
from urllib.parse import urlsplit

import httpx

from ..config import USER_AGENT

log = logging.getLogger("astra.http")

ALLOWED_HOSTS: frozenset[str] = frozenset({
    "irsa.ipac.caltech.edu",
    "gea.esac.esa.int",
    "simbad.harvard.edu",
    "simbad.cds.unistra.fr",
    "cds.unistra.fr",
    "vizier.idia.ac.za",
    "vizier.cds.unistra.fr",
    "ssp.imcce.fr",
    "generativelanguage.googleapis.com",
})

RETRY_STATUS = frozenset({502, 503, 504})
BACKOFF_S = (1.0, 3.0, 9.0)
_RETRY_EXC = (
    httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout,
    httpx.WriteTimeout, httpx.RemoteProtocolError, httpx.ReadError,
)

_client: Optional[httpx.AsyncClient] = None
_client_loop: Optional[asyncio.AbstractEventLoop] = None


def check_allowed(url: str) -> None:
    """Raise ValueError unless ``url`` is http(s) and its host is allow-listed."""
    parts = urlsplit(str(url))
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme not allowed: {parts.scheme!r}")
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"host not allow-listed: {host!r}")


async def _guard_request(request: httpx.Request) -> None:
    # Called for the initial request and again for every redirect hop.
    check_allowed(str(request.url))


def _new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        max_redirects=5,
        timeout=httpx.Timeout(30.0, connect=10.0),
        limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        event_hooks={"request": [_guard_request]},
    )


def get_client() -> httpx.AsyncClient:
    """Shared client (one per event loop)."""
    global _client, _client_loop
    try:
        loop: Optional[asyncio.AbstractEventLoop] = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if _client is None or _client.is_closed or (loop is not None and _client_loop is not loop):
        _client = _new_client()
        _client_loop = loop
    return _client


async def aclose() -> None:
    global _client, _client_loop
    c, _client, _client_loop = _client, None, None
    if c is not None and not c.is_closed:
        try:
            await c.aclose()
        except Exception:  # client may belong to a closed loop
            pass


def _delay(attempt: int) -> float:
    return BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)]


async def fetch(
    method: str,
    url: str,
    *,
    params: Any = None,
    data: Any = None,
    json: Any = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 30,
    retries: int = 3,
    raise_for_status: bool = True,
) -> httpx.Response:
    """Allow-listed request with retries (502/503/504/timeouts, backoff 1/3/9 s).

    Raises ``ValueError`` for a disallowed host, ``httpx.HTTPError`` when retries are exhausted. With
    ``raise_for_status=False`` a final 4xx/5xx response is returned instead of raised.
    """
    check_allowed(url)
    for attempt in range(retries + 1):
        try:
            resp = await get_client().request(
                method, url, params=params, data=data, json=json, headers=headers,
                timeout=timeout,
            )
        except _RETRY_EXC as e:
            if attempt < retries:
                log.info("retry %d for %s after %s", attempt + 1, urlsplit(url).netloc, type(e).__name__)
                await asyncio.sleep(_delay(attempt))
                continue
            raise
        if resp.status_code in RETRY_STATUS and attempt < retries:
            log.info("retry %d for %s after HTTP %d", attempt + 1, urlsplit(url).netloc, resp.status_code)
            await asyncio.sleep(_delay(attempt))
            continue
        if raise_for_status:
            resp.raise_for_status()
        return resp
    raise RuntimeError("unreachable")  # pragma: no cover


@asynccontextmanager
async def stream(
    method: str,
    url: str,
    *,
    params: Any = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 60,
    retries: int = 3,
) -> AsyncIterator[httpx.Response]:
    """Streaming request (for cutouts). Retries only until the response headers arrive.

    ``async with stream("GET", url) as resp: async for chunk in resp.aiter_bytes(): ...``
    The response is always closed on exit. A non-2xx final status raises ``httpx.HTTPStatusError``.
    """
    check_allowed(url)
    client = get_client()
    resp: Optional[httpx.Response] = None
    for attempt in range(retries + 1):
        req = client.build_request(method, url, params=params, headers=headers, timeout=timeout)
        try:
            resp = await client.send(req, stream=True)
        except _RETRY_EXC:
            if attempt < retries:
                await asyncio.sleep(_delay(attempt))
                continue
            raise
        if resp.status_code in RETRY_STATUS and attempt < retries:
            await resp.aclose()
            await asyncio.sleep(_delay(attempt))
            continue
        break
    assert resp is not None
    try:
        if resp.status_code >= 400:
            await resp.aread()
            resp.raise_for_status()
        yield resp
    finally:
        await resp.aclose()
