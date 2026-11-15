"""Live status table of every external dependency.

Run from ``backend/``:  ``uv run python -m scripts.probe_endpoints``
The Gemini key (if configured) is sent as a header and is NEVER printed.
"""
from __future__ import annotations

import asyncio
import sys
import time
from typing import Awaitable, Callable

import httpx

from app import models
from app.config import get_settings
from app.services import cutouts, http, irsa_sia

BARNARD = (269.452, 4.6934)
GAIA_Q = "SELECT TOP 1 source_id FROM gaiadr3.gaia_source"
SIMBAD_Q = "SELECT TOP 1 main_id FROM basic"
IRSA_Q = "SELECT TOP 1 table_name FROM TAP_SCHEMA.tables"
TAP_BASE = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv"}

Result = tuple[bool, str]  # (ok, note)


async def _http_probe(url: str, *, params=None, headers=None, timeout: float = 25, ok_text: str | None = None) -> Result:
    resp = await http.fetch("GET", url, params=params, headers=headers, timeout=timeout, retries=1,
                            raise_for_status=False)
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}"
    if ok_text is not None and ok_text not in resp.text:
        return False, f"HTTP 200 but missing {ok_text!r}"
    return True, f"HTTP 200, {len(resp.content)} B"


async def probe_sia(collection: str) -> Result:
    exps, status = await irsa_sia.query_exposures(BARNARD[0], BARNARD[1], [collection])
    st = status.get(collection, "error")
    return st == "ok", f"{st}, {len(exps)} detector images"


async def probe_cutout() -> Result:
    exps, status = await irsa_sia.query_exposures(BARNARD[0], BARNARD[1], ["spherex_dr1"])
    if not exps:
        return False, f"no exposures (SIA {status.get('spherex_dr1')})"
    exp: models.Exposure = exps[0]
    path = await cutouts.fetch_cutout(exp, BARNARD[0], BARNARD[1], 0.02)
    cut = await asyncio.to_thread(cutouts.load_cutout, path, exp)
    return True, f"{exp.obs_id} D{exp.detector}: {path.stat().st_size / 1024:.0f} KB on disk, shape {cut.image.shape}"


async def probe_gemini() -> Result:
    key = get_settings().gemini_api_key
    if not key:
        return False, "no GEMINI_API_KEY configured (template explanations only)"
    return await _http_probe(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": key}, timeout=20, ok_text="models",
    )


def _probes() -> list[tuple[str, Callable[[], Awaitable[Result]]]]:
    s = get_settings()
    simbad = {"harvard": s.simbad_urls[0] if s.simbad_urls else "https://simbad.harvard.edu/simbad/sim-tap/sync",
              "cds": "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"}
    return [
        ("IRSA SIA2 spherex_dr1", lambda: probe_sia("spherex_dr1")),
        ("IRSA SIA2 spherex_qr3", lambda: probe_sia("spherex_qr3")),
        ("IRSA cutout (stream, 0.02 deg)", probe_cutout),
        ("Gaia DR3 TAP (ESA)", lambda: _http_probe(s.gaia_tap_url, params={**TAP_BASE, "QUERY": GAIA_Q})),
        ("SIMBAD TAP (Harvard)", lambda: _http_probe(simbad["harvard"], params={**TAP_BASE, "QUERY": SIMBAD_Q}, timeout=15)),
        ("SIMBAD TAP (CDS)", lambda: _http_probe(simbad["cds"], params={**TAP_BASE, "QUERY": SIMBAD_Q}, timeout=15)),
        ("Sesame (CDS)", lambda: _http_probe(
            "https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/SNV?Barnard%27s%20star", timeout=20, ok_text="jradeg")),
        ("SkyBoT (IMCCE)", lambda: _http_probe(
            "https://ssp.imcce.fr/webservices/skybot/api/conesearch.php",
            params={"-ep": "2461000.5", "-ra": "269.452", "-dec": "4.693", "-rd": "0.05", "-mime": "json",
                    "-loc": "500", "-output": "basic"}, timeout=20)),
        ("IRSA TAP", lambda: _http_probe(s.irsa_tap_url, params={**TAP_BASE, "QUERY": IRSA_Q}, timeout=20)),
        ("Gemini models list", probe_gemini),
    ]


async def _run_one(name: str, fn: Callable[[], Awaitable[Result]]) -> tuple[str, str, float, str]:
    t0 = time.perf_counter()
    try:
        ok, note = await asyncio.wait_for(fn(), timeout=150)
        status = "OK" if ok else "FAIL"
    except asyncio.TimeoutError:
        status, note = "FAIL", "timeout"
    except (httpx.HTTPError, ValueError, OSError) as e:
        status, note = "FAIL", f"{type(e).__name__}: {str(e)[:100]}"
    except Exception as e:  # keep probing the other services
        status, note = "FAIL", f"{type(e).__name__}: {str(e)[:100]}"
    return name, status, time.perf_counter() - t0, note


async def main() -> int:
    rows = []
    for name, fn in _probes():  # sequential: be polite to the services and keep timings meaningful
        rows.append(await _run_one(name, fn))
    await http.aclose()
    w = max(len(r[0]) for r in rows)
    print(f"{'service'.ljust(w)}  status  time(s)  note")
    print("-" * (w + 40))
    for name, status, dt, note in rows:
        print(f"{name.ljust(w)}  {status.ljust(6)}  {dt:6.1f}  {note}")
    return 0 if all(r[1] == "OK" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
