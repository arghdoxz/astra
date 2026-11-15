"""HTTP routes per docs/API_CONTRACT.md."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response

from .. import db, jobs
from ..config import VERSION, get_settings
from ..models import (
    AnnotationIn, ExplainRequest, Explanation, Frame, Investigation, InvestigationRequest, ObservationsResponse,
)
from ..pipeline import frame_file, thumb_file

router = APIRouter(prefix="/api")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, detail=None):
        self.status, self.code, self.message, self.detail = status, code, message, detail


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?"))


def _load(inv_id: str) -> Investigation:
    live = jobs.get_live(inv_id)
    if live is not None:
        return live
    j = db.get_investigation_json(inv_id)
    if j is None:
        raise ApiError(404, "not_found", f"Investigation {inv_id} not found.")
    return Investigation.model_validate_json(j)


def _png(path) -> Response:
    if not path.exists():
        raise ApiError(404, "frame_not_found", "Frame not available.")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


# ---------------- health
_health_cache: dict = {"t": 0.0, "v": None}


@router.get("/health")
async def health(deep: int = 0):
    now = time.time()
    if not deep and _health_cache["v"] and now - _health_cache["t"] < 300:
        return _health_cache["v"]
    from ..services import http

    S = get_settings()

    async def probe(url, params=None, headers=None, timeout=8.0) -> str:
        try:
            r = await http.fetch("GET", url, params=params, headers=headers, timeout=timeout, retries=0)
            return "ok" if r.status_code < 400 else ("degraded" if r.status_code < 500 else "down")
        except Exception:
            return "down"

    import asyncio

    sia, gaia, simbad, skybot = await asyncio.gather(
        probe("https://irsa.ipac.caltech.edu/SIA", {"COLLECTION": "spherex_dr1", "POS": "circle 0 0 0.0001", "MAXREC": "1"}, timeout=25.0),
        probe(S.gaia_tap_url, {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
                               "QUERY": "SELECT TOP 1 source_id FROM gaiadr3.gaia_source"}),
        probe(S.simbad_urls[0], {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
                                 "QUERY": "SELECT TOP 1 main_id FROM basic"}),
        probe("https://ssp.imcce.fr/webservices/skybot/api/conesearch.php",
              {"-ep": "2460600.5", "-ra": "0", "-dec": "0", "-rd": "0.01", "-mime": "json", "-loc": "500",
               "-output": "basic"}, timeout=12.0),
    )
    services = {"irsa_sia": sia, "gaia": gaia, "simbad": simbad, "skybot": skybot,
                "gemini": "ok" if S.gemini_enabled else "disabled"}
    overall = "ok" if all(s in ("ok", "disabled") for s in services.values()) else "degraded"
    v = {"status": overall, "version": VERSION, "services": services,
         "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    _health_cache.update(t=now, v=v)
    return v


# ---------------- resolve / observations / crossmatch
@router.get("/resolve")
async def resolve(q: str = Query(..., min_length=1, max_length=100)):
    from ..services import resolver

    try:
        return (await resolver.resolve(q)).model_dump(by_alias=True)
    except LookupError:
        raise ApiError(404, "not_found", f"Could not resolve '{q}'. Try coordinates like '133.795 -7.245'.")


@router.get("/targets")
async def targets():
    from ..services import resolver

    return {"items": resolver.BUILTIN_TARGETS}


@router.get("/observations")
async def observations(ra: float = Query(..., ge=0, lt=360), dec: float = Query(..., ge=-90, le=90),
                       collections: Optional[str] = None):
    from ..services import irsa_sia

    cols = [c for c in (collections or ",".join(get_settings().collections)).split(",") if c in get_settings().collections]
    exps, status = await irsa_sia.query_exposures(ra, dec, cols)
    visits = irsa_sia.group_visits(exps)
    counts = {c: sum(1 for e in exps if e.collection == c) for c in cols}
    return ObservationsResponse(
        ra=ra, dec=dec, collections=[{"name": c, "status": status.get(c, "unknown"), "n": counts.get(c, 0)} for c in cols],
        exposures=exps, visits=visits).model_dump()


@router.get("/crossmatch")
async def crossmatch(ra: float = Query(..., ge=0, lt=360), dec: float = Query(..., ge=-90, le=90),
                     radius_arcsec: float = Query(30, ge=1, le=180), mjd: Optional[float] = None):
    from ..services import crossmatch as xm

    m = mjd if mjd is not None else 60900.0
    res = await xm.crossmatch_all(ra, dec, radius_arcsec, m)
    return res.model_dump(by_alias=True)


# ---------------- investigations
@router.post("/investigations", status_code=202)
async def create_investigation(req: InvestigationRequest, request: Request):
    if not jobs.inv_limiter.allow(_ip(request)):
        raise ApiError(429, "rate_limited", "Too many investigations; please wait a minute.")
    req.detectors = sorted({d for d in req.detectors if 1 <= d <= 6}) or [1, 2, 3, 4, 5, 6]
    inv_id, status = await jobs.submit(req)
    return {"id": inv_id, "status": status}


@router.get("/investigations")
async def list_investigations(limit: int = Query(20, ge=1, le=100)):
    return {"items": db.list_investigations(limit)}


@router.get("/investigations/{inv_id}")
async def get_investigation(inv_id: str):
    return Response(_load(inv_id).model_dump_json(by_alias=True), media_type="application/json")


def _check_frame(inv: Investigation, **kw) -> Frame:
    for f in inv.frames:
        if all(str(getattr(f, k)) == str(v) for k, v in kw.items()):
            return f
    raise ApiError(404, "frame_not_found", "No such frame in this investigation.")


@router.get("/investigations/{inv_id}/frames/{visit_id}/{det}.png")
async def frame_stack(inv_id: str, visit_id: str, det: str):
    inv = _load(inv_id)
    return _png(frame_file(inv_id, _check_frame(inv, kind="visit_stack", visit_id=visit_id, detector=det)))


@router.get("/investigations/{inv_id}/exposures/{obs_id}/{det}.png")
async def frame_exposure(inv_id: str, obs_id: str, det: str):
    inv = _load(inv_id)
    return _png(frame_file(inv_id, _check_frame(inv, kind="exposure", obs_id=obs_id, detector=det)))


@router.get("/investigations/{inv_id}/diff/{visit_a}/{visit_b}/{det}.png")
async def frame_diff(inv_id: str, visit_a: str, visit_b: str, det: str, method: str = "simple"):
    inv = _load(inv_id)
    f = _check_frame(inv, kind="diff", visit_id=visit_a, visit_b=visit_b, detector=det, method=method)
    return _png(frame_file(inv_id, f))


@router.get("/investigations/{inv_id}/flags/{visit_id}/{det}.png")
async def frame_flags(inv_id: str, visit_id: str, det: str):
    inv = _load(inv_id)
    return _png(frame_file(inv_id, _check_frame(inv, kind="flags", visit_id=visit_id, detector=det)))


@router.get("/investigations/{inv_id}/thumbs/{cid}/{visit_id}.png")
async def frame_thumb(inv_id: str, cid: str, visit_id: str):
    inv = _load(inv_id)
    c = next((c for c in inv.candidates if c.id == cid), None)
    if c is None or not any(t.visit_id == visit_id for t in c.thumbnails):
        raise ApiError(404, "frame_not_found", "No such thumbnail.")
    return _png(thumb_file(inv_id, cid, visit_id))


# ---------------- explain
@router.post("/investigations/{inv_id}/explain")
async def explain(inv_id: str, body: ExplainRequest, request: Request):
    inv = _load(inv_id)
    if inv.status != "done":
        raise ApiError(409, "not_ready", "The investigation has not finished yet.")
    if body.subject == "candidate" and not any(c.id == body.candidate_id for c in inv.candidates):
        raise ApiError(404, "not_found", "Unknown candidate.")
    k = hashlib.sha1(f"{inv_id}|{body.subject}|{body.candidate_id}|{body.question or ''}".encode()).hexdigest()
    cached = db.explain_get(k)
    if cached:
        return Response(cached, media_type="application/json")
    if not jobs.explain_limiter.allow(_ip(request)):
        raise ApiError(429, "rate_limited", "Too many explanation requests; please wait a minute.")
    from ..ai.explain import explain as do_explain

    ex: Explanation = await do_explain(inv, body)
    j = ex.model_dump_json()
    db.explain_put(k, j)
    return Response(j, media_type="application/json")


# ---------------- annotations / review queue
def _valid_cid(cid: str) -> None:
    inv_id, _, sub = cid.partition(":")
    if not sub:
        raise ApiError(400, "bad_candidate_id", "candidate_id must be '{investigation_id}:{cid}'.")
    inv = _load(inv_id)
    if sub != "target" and not any(c.id == sub for c in inv.candidates):
        raise ApiError(404, "not_found", "Unknown candidate.")


@router.get("/candidates/{candidate_id}/annotations")
async def get_annotations(candidate_id: str):
    from .. import db_annotations as da

    _valid_cid(candidate_id)
    with db.locked():
        return da.list_annotations(db.annotations_conn(), candidate_id).model_dump()


@router.post("/candidates/{candidate_id}/annotations")
async def post_annotation(candidate_id: str, body: AnnotationIn, request: Request):
    from .. import db_annotations as da

    if not jobs.annot_limiter.allow(_ip(request)):
        raise ApiError(429, "rate_limited", "Too many annotations; please wait a minute.")
    _valid_cid(candidate_id)
    with db.locked():
        da.insert_annotation(db.annotations_conn(), candidate_id, body)
        return da.list_annotations(db.annotations_conn(), candidate_id).model_dump()


@router.get("/candidates")
async def review_queue(limit: int = Query(50, ge=1, le=200)):
    from .. import db_annotations as da

    items = []
    for d in db.done_investigations(100):
        inv_id = d["id"]
        name = (d.get("request") or {}).get("name") or (d.get("target") or {}).get("name")
        ev = d.get("evidence") or {}
        t = d.get("target") or {}
        items.append({"candidate_id": f"{inv_id}:target", "investigation_id": inv_id, "name": name,
                      "ra": t.get("ra"), "dec": t.get("dec"), "kind": "target",
                      "classification": ev.get("classification", "insufficient_data"),
                      "confidence": ev.get("confidence", "insufficient"), "thumbnail_url": None})
        for c in d.get("candidates") or []:
            cev = c.get("evidence") or {}
            th = (c.get("thumbnails") or [{}])[0].get("url")
            items.append({"candidate_id": f"{inv_id}:{c['id']}", "investigation_id": inv_id, "name": name,
                          "ra": c["ra"], "dec": c["dec"], "kind": c["kind"],
                          "classification": cev.get("classification", "insufficient_data"),
                          "confidence": cev.get("confidence", "insufficient"), "thumbnail_url": th})
    # unexplained / higher-confidence first
    order = {"unexplained_needs_review": 0, "low_confidence_change": 1}
    conf = {"strong": 0, "moderate": 1, "low": 2, "insufficient": 3}
    items.sort(key=lambda i: (order.get(i["classification"], 2), conf.get(i["confidence"], 4)))
    items = items[:limit]
    with db.locked():
        tallies = da.tallies(db.annotations_conn(), [i["candidate_id"] for i in items])
    for i in items:
        i["tally"] = tallies.get(i["candidate_id"], {"real": 0, "artifact": 0, "known": 0, "unsure": 0})
    return {"items": items}


# ---------------- reports
def _annotations_for(inv: Investigation) -> dict:
    from .. import db_annotations as da

    cids = [f"{inv.id}:target"] + [f"{inv.id}:{c.id}" for c in inv.candidates]
    out = {}
    with db.locked():
        for cid in cids:
            al = da.list_annotations(db.annotations_conn(), cid)
            if al.annotations:
                out[cid] = al.model_dump()
    return out


@router.get("/investigations/{inv_id}/report.json")
async def report_json(inv_id: str):
    inv = _load(inv_id)
    d = json.loads(inv.model_dump_json(by_alias=True))
    d["annotations"] = _annotations_for(inv)
    k = hashlib.sha1(f"{inv_id}|target|None|".encode()).hexdigest()
    ex = db.explain_get(k)
    d["ai_explanation"] = json.loads(ex) if ex else None
    return JSONResponse(d, headers={"Content-Disposition": f'attachment; filename="astra_{inv_id}.json"'})


@router.get("/investigations/{inv_id}/report.csv")
async def report_csv(inv_id: str):
    inv = _load(inv_id)
    buf = io.StringIO()
    cols = ["obs_id", "visit_id", "detector", "mjd", "wavelength_um", "bandwidth_um", "flux_ujy", "flux_err_ujy",
            "ab_mag", "snr", "saturated", "flagged_frac", "contamination_bits", "apcorr", "apcorr_method", "outlier",
            "rel_flux"]
    w = csv.writer(buf)
    w.writerow(cols)
    for p in inv.photometry:
        d = p.model_dump()
        d["contamination_bits"] = ";".join(p.contamination_bits)
        w.writerow([d.get(c) for c in cols])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="astra_{inv_id}_photometry.csv"'})


@router.get("/investigations/{inv_id}/report.md")
async def report_md(inv_id: str):
    inv = _load(inv_id)
    ev = inv.evidence
    t = inv.target
    L = [f"# ASTRA investigation report — {t.name or 'field'}", "",
         f"- Investigation: `{inv.id}` ({inv.generated_from}), generated {inv.provenance.generated_at}",
         f"- Position: RA {t.ra:.5f}°, Dec {t.dec:.5f}° (ICRS; source: {t.source})",
         f"- Field of view: {inv.request.fov_arcmin}′; detectors {inv.request.detectors}",
         f"- Data: {', '.join(inv.provenance.collections)}; pipeline versions {', '.join(inv.provenance.pipeline_versions) or 'n/a'}; "
         f"{inv.provenance.n_exposures_used} of {inv.provenance.n_exposures_found} exposures used ({inv.provenance.sampling})",
         "", "## Assessment", "",
         f"**{ev.classification_label}** — confidence tier **{ev.confidence}** ({ev.confidence_reason}); novelty: {ev.novelty}.",
         "", ev.summary, "", "| Evidence | Value | Threshold | Verdict | Explanation |", "|---|---|---|---|---|"]
    for it in ev.items:
        val = "—" if it.value is None else f"{it.value}{' ' + it.unit if it.unit else ''}"
        L.append(f"| {it.label} | {val} | {it.threshold or ''} | {it.verdict} | {it.explanation.replace('|', '/')} |")
    if inv.astrometry.fit:
        f = inv.astrometry.fit
        L += ["", "## Motion", "",
              f"Measured PM µα* = {f.pm_ra:.1f} ± {f.pm_ra_err:.1f}, µδ = {f.pm_dec:.1f} ± {f.pm_dec_err:.1f} mas/yr "
              f"(baseline {f.baseline_yr:.2f} yr, χ²_red {f.chi2_red:.2f}, parallax {f.parallax_mode})."]
    if inv.lightcurve.metrics:
        L += ["", "## Brightness", "", "| Detector | n | χ²_red | amp σ | frac amp | significant |", "|---|---|---|---|---|---|"]
        for m in inv.lightcurve.metrics:
            L.append(f"| D{m.detector} | {m.n} | {m.chi2_red} | {m.amp_sigma} | {m.frac_amp} | {m.significant} |")
        L += ["", inv.lightcurve.period_note]
    if inv.candidates:
        L += ["", "## Field change candidates", "", "| id | kind | RA | Dec | peak Z | classification | confidence |",
              "|---|---|---|---|---|---|---|"]
        for c in inv.candidates:
            L.append(f"| {c.id} | {c.kind} | {c.ra:.5f} | {c.dec:.5f} | {c.peak_z:.1f} | "
                     f"{c.evidence.classification_label} | {c.evidence.confidence} |")
    ann = _annotations_for(inv)
    if ann:
        L += ["", "## Human annotations", ""]
        for cid, al in ann.items():
            L.append(f"- `{cid}`: {al['tally']}")
            for a in al["annotations"][:10]:
                L.append(f"  - {a['verdict']}: {a['note']}")
    if inv.warnings:
        L += ["", "## Warnings", ""] + [f"- {w}" for w in inv.warnings]
    L += ["", "## Methods", ""] + [f"- **{m.label}** ({'implemented' if m.implemented else 'not implemented'}): {m.description}"
                                   for m in inv.methods]
    L += ["", "---", "Data: NASA SPHEREx via NASA/IPAC IRSA; Gaia DR3 (ESA); SIMBAD (CDS); CatWISE2020; SkyBoT (IMCCE). "
          "ASTRA is not affiliated with or endorsed by NASA. Confidence tiers are rule-based, not probabilities."]
    return PlainTextResponse("\n".join(L), media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="astra_{inv_id}.md"'})
