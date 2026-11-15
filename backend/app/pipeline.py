"""Investigation pipeline (Opus). resolve → discover → select → fetch → stack → render → measure → crossmatch → candidates → score.

All CPU-heavy work runs in worker threads (anyio.to_thread). Partial results are pushed through progress_cb after
each stage so the UI fills in progressively.
"""
from __future__ import annotations

import asyncio
import logging
import math
from collections import defaultdict
from pathlib import Path
from typing import Awaitable, Callable, Optional

import anyio
import numpy as np

from .config import SOFTWARE, get_settings
from .core_types import CutoutData, DiffContext, EvidenceInput, GridSpec, Stack
from .models import (
    Astrometry, AstrometryCatalog, AstrometryMeasured, Candidate, CandidateMotion, CatalogMatch, CatalogResult,
    CrossMatch, ErrorInfo, Exposure, Frame, Investigation, InvestigationRequest, MethodNote, PhotPoint, Progress,
    Provenance, RequestEcho, Stretch, Target, Thumbnail, TrackPoint,
)

log = logging.getLogger("astra.pipeline")
ProgressCb = Callable[[Investigation], Awaitable[None]]

VARIABLE_OTYPES = {
    "V*", "Mi*", "LP*", "TT*", "Or*", "RR*", "Ce*", "EB*", "Pu*", "Ir*", "Er*", "Ro*", "AB*", "C*", "S*",
    "Y*O", "Y*?", "TT?", "Mi?", "LP?", "V*?", "RI*", "Fl*", "bL*", "El*", "WU*", "SN*", "No*",
}
IDENTITY_RADIUS = {"gaia": 3.0, "simbad": 3.0, "catwise": 5.0, "skybot": 15.0}


class PipelineError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- paths
def inv_dir(inv_id: str) -> Path:
    """All files of one investigation live under cache/inv/{id}/ (frames in frames/)."""
    return get_settings().cache_dir / "inv" / inv_id


def frame_file(inv_id: str, frame: Frame) -> Path:
    """Local PNG path for a Frame of this investigation. Used by API routes and precompute_targets.py."""
    d = inv_dir(inv_id) / "frames"
    det = frame.detector
    if frame.kind == "visit_stack":
        return d / f"stack_{frame.visit_id}_{det}.png"
    if frame.kind == "exposure":
        return d / f"exp_{_safe(frame.obs_id)}_{det}.png"
    if frame.kind == "flags":
        return d / f"flags_{frame.visit_id}_{det}.png"
    if frame.kind == "diff":
        return d / f"diff_{frame.visit_id}_{frame.visit_b}_{det}_{frame.method or 'simple'}.png"
    raise ValueError(frame.kind)


def thumb_file(inv_id: str, cid: str, visit_id: str) -> Path:
    return inv_dir(inv_id) / "frames" / f"thumb_{cid}_{visit_id}.png"


def _safe(s: Optional[str]) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in (s or ""))


# ---------------------------------------------------------------- helpers
def _mjd_to_jyear(mjd: float) -> float:
    return 2000.0 + (mjd - 51544.5) / 365.25


def _sep_arcsec(ra1, dec1, ra2, dec2) -> float:
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    s = math.sin((d2 - d1) / 2) ** 2 + math.cos(d1) * math.cos(d2) * math.sin((r2 - r1) / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(s)))) * 3600


def _finite(x) -> Optional[float]:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _methods(cutout_mode: str) -> list[MethodNote]:
    return [
        MethodNote(key="data", label="Real SPHEREx L2 images",
                   description="DR1 + QR3 spectral images discovered with IRSA SIA2; small cutouts via the IRSA cutout service.",
                   implemented=True),
        MethodNote(key="background", label="Background",
                   description="SPHEREx ZODI model subtracted, then a per-cutout sigma-clipped median; "
                               "local annulus background for photometry.",
                   implemented=True),
        MethodNote(key="registration", label="Registration",
                   description="Every exposure reprojected onto one north-up TAN grid (6.15″/px) using its own WCS (bilinear). "
                               "Gaia-based offsets are measured and reported, not applied.", implemented=True),
        MethodNote(key="stacking", label="Visit stacks",
                   description="Inverse-variance weighted mean per visit and detector; hard-flagged pixels masked; SOURCE flag never masked.",
                   implemented=True),
        MethodNote(key="diff_simple", label="Difference imaging — simple",
                   description="Z = (S_b − S_a)/√(V_a+V_b) on registered stacks with combined masks; flux scale checked.",
                   implemented=True),
        MethodNote(key="diff_psf", label="Difference imaging — PSF-matched (Gaussian approximation)",
                   description="Sharper stack convolved with a Gaussian from the header PSF_FWHM difference; variance propagated. "
                               "This is NOT ZOGY or Alard–Lupton.", implemented=True),
        MethodNote(key="zogy", label="ZOGY / full PSF-matched subtraction", description="Not implemented.", implemented=False),
        MethodNote(key="photometry", label="Aperture photometry",
                   description="r = 1 FWHM, annulus 2–3.5 FWHM, MJy/sr → µJy via pixel solid angle, ePSF or Gaussian aperture "
                               "correction; saturated apertures reported as lower limits.", implemented=True),
        MethodNote(key="spectrum", label="On-the-fly spectrum",
                   description="Each exposure gives one (λ, F) point; λ from the WCS-WAVE table at the target pixel; binned to 102 channels.",
                   implemented=True),
        MethodNote(key="astrometry", label="Astrometry",
                   description="2-D Gaussian centroids on visit stacks; weighted linear PM fit with catalog parallax "
                               "(free parallax when ≥4 epochs over ≥1 yr).", implemented=True),
        MethodNote(key="period", label="Period finding", description="Not attempted: too few epochs.", implemented=False),
        MethodNote(key="saturated_psf", label="Saturated-star PSF fitting", description="Not implemented.", implemented=False),
        MethodNote(key="evidence", label="Evidence tiers",
                   description="Rule-based confidence tiers and deterministic classification; not calibrated probabilities.",
                   implemented=True),
    ]


async def _emit(inv: Investigation, cb: Optional[ProgressCb], stage: str, pct: float, msg: str) -> None:
    inv.progress = Progress(stage=stage, pct=round(pct, 1), message=msg)  # type: ignore[arg-type]
    inv.status = "running"
    if cb:
        await cb(inv)


# ---------------------------------------------------------------- main
async def run_investigation(
    inv_id: str, req: InvestigationRequest, progress_cb: Optional[ProgressCb] = None
) -> Investigation:
    from .services import calib_cache, crossmatch, cutouts, irsa_sia, resolver
    from .science import ephemeris

    S = get_settings()
    from .db import now_iso

    inv = Investigation(
        id=inv_id, status="running",
        request=RequestEcho(ra=req.ra, dec=req.dec, fov_arcmin=req.fov_arcmin, name=req.name, detectors=req.detectors),
        target=Target(name=req.name, ra=req.ra, dec=req.dec, source="coordinates"),
        created_at=now_iso(), methods=_methods(S.cutout_mode),
    )
    services: dict[str, str] = {}

    # ---------------- resolve
    await _emit(inv, progress_cb, "resolve", 2, "Resolving target and proper motion")
    target = Target(name=req.name, ra=req.ra, dec=req.dec, source="coordinates")
    builtin = None
    try:
        builtin = resolver.match_builtin(req.ra, req.dec)
    except Exception:
        log.exception("match_builtin failed")
    if builtin:
        target = Target(name=req.name or builtin["name"], ra=builtin["ra"], dec=builtin["dec"],
                        pm_ra=builtin.get("pm_ra"), pm_dec=builtin.get("pm_dec"), parallax=builtin.get("parallax"),
                        ref_epoch=builtin.get("ref_epoch", 2000.0), source="builtin", otype=builtin.get("otype"))
        cra, cdec = builtin.get("challenge_ra"), builtin.get("challenge_dec")
        if cra is not None and _sep_arcsec(req.ra, req.dec, cra, cdec) < 30:
            inv.warnings.append(
                f"The requested coordinates match {builtin['name']} at its ~2010 (WISE-era) position. "
                "ASTRA propagated its catalogued proper motion to each SPHEREx exposure epoch.")
    elif req.name:
        try:
            r = await resolver.resolve(req.name)
            if _sep_arcsec(r.ra, r.dec, req.ra, req.dec) < 600:
                target = Target(**r.model_dump(include=set(Target.model_fields)))
        except Exception:
            pass
    if not req.propagate_pm:
        target.pm_ra = target.pm_dec = None
    inv.target = target
    has_pm = target.pm_ra is not None and target.pm_dec is not None

    def pos_at(mjd: float) -> tuple[float, float]:
        if not has_pm:
            return target.ra, target.dec
        return ephemeris.predict_track(target, [mjd])[0]

    # ---------------- discover
    await _emit(inv, progress_cb, "discover", 6, "Searching SPHEREx DR1 + QR3 (IRSA SIA2)")
    q_ra, q_dec = pos_at(60900.0)  # ~2025.6, middle of the SPHEREx DR1/QR3 window
    exposures, coll_status = await irsa_sia.query_exposures(q_ra, q_dec, S.collections)
    for c, st in coll_status.items():
        services[f"irsa_sia:{c}"] = st
    if all(st != "ok" for st in coll_status.values()):
        raise PipelineError("irsa_unavailable", "IRSA SPHEREx search is unavailable right now (all collections failed).")
    for c, st in coll_status.items():
        if st != "ok":
            inv.warnings.append(f"Collection {c} could not be searched ({st}); results use the other release(s).")
    if not exposures:
        failed = [c for c, st in coll_status.items() if st != "ok"]
        if failed:
            raise PipelineError("irsa_unavailable", f"No exposures found, but {', '.join(failed)} could not be searched "
                                "(IRSA error); coverage is unknown. Please retry later.")
        raise PipelineError("no_coverage", "SPHEREx DR1/QR3 has no exposures covering this position yet.")
    n_found = len(exposures)
    irsa_sia.group_visits(exposures)
    selected, sampling = irsa_sia.select_exposures(exposures, min(req.max_exposures, S.max_exposures), req.detectors)
    if not selected:
        raise PipelineError("no_coverage", "No exposures for the selected detectors.")
    visits = irsa_sia.group_visits(selected)  # recompute visits over the selection (ids v0.. in time order)
    mjds = [e.mjd for e in selected]
    mean_mjd = float(np.mean(mjds))
    c_ra, c_dec = pos_at(mean_mjd)
    inv.visits = visits
    inv.exposures = sorted(selected, key=lambda e: (e.mjd, e.detector))
    inv.provenance = Provenance(collections=S.collections, n_exposures_found=n_found, n_exposures_used=len(selected),
                                sampling=sampling, services={}, generated_at=now_iso(), software=SOFTWARE)  # type: ignore[arg-type]
    if sampling != "all":
        inv.warnings.append(f"{n_found} exposures found; {len(selected)} were sampled evenly in time per visit and detector.")

    # ---------------- fetch
    size_deg = req.fov_arcmin / 60.0 * 1.55 + 0.004
    await _emit(inv, progress_cb, "fetch", 10, f"Downloading {len(selected)} cutouts")
    by_id: dict[tuple[str, int], Exposure] = {(e.obs_id, e.detector): e for e in inv.exposures}  # obs_id is shared by up to 6 detectors
    paths: dict[tuple[str, int], Path] = {}

    async def _one(e: Exposure):
        ra_e, dec_e = pos_at(e.mjd) if has_pm else (c_ra, c_dec)
        try:
            p = await cutouts.fetch_cutout(e, ra_e, dec_e, size_deg)
            return (e.obs_id, e.detector), p
        except Exception as ex:  # noqa: BLE001
            log.warning("cutout %s failed: %s", e.obs_id, ex)
            return (e.obs_id, e.detector), None

    tasks = [asyncio.create_task(_one(e)) for e in inv.exposures]
    done_n = 0
    for fut in asyncio.as_completed(tasks):
        oid, p = await fut
        done_n += 1
        if p is None:
            by_id[oid].status = "failed"
        else:
            paths[oid] = p
        if done_n % 8 == 0 or done_n == len(tasks):
            await _emit(inv, progress_cb, "fetch", 10 + 45 * done_n / len(tasks), f"Cutouts {done_n}/{len(tasks)}")
    n_failed = sum(1 for e in inv.exposures if e.status == "failed")
    if not paths:
        raise PipelineError("irsa_unavailable", "All cutout downloads failed (IRSA cutout service unavailable).")
    if n_failed > 0.2 * len(inv.exposures):
        inv.warnings.append(f"{n_failed} of {len(inv.exposures)} cutouts failed to download and were skipped.")

    # load cutouts (thread)
    def _load_all() -> dict[tuple[str, int], CutoutData]:
        out = {}
        for oid, p in paths.items():
            try:
                out[oid] = cutouts.load_cutout(p, by_id[oid])
            except Exception as ex:  # noqa: BLE001
                log.warning("load %s failed: %s", oid, ex)
                by_id[oid].status = "failed"
        return out

    cuts = await anyio.to_thread.run_sync(_load_all)
    if not cuts:
        raise PipelineError("bad_data", "Downloaded cutouts could not be read.")

    # calibration (λ tables + ePSF), once per (detector, version)
    calib: dict[tuple[int, str], Optional[Path]] = {}
    for oid, cut in cuts.items():
        k = (cut.detector, cut.version)
        if k not in calib:
            try:
                calib[k] = await calib_cache.ensure_calib(cut.detector, cut.version, by_id[oid], c_ra, c_dec)
            except Exception:  # noqa: BLE001
                log.exception("calib failed")
                calib[k] = None
    if any(v is None for v in calib.values()):
        inv.warnings.append("Wavelength calibration table unavailable for some detectors; λ approximated from the band centre.")

    # per-exposure metadata
    wl_sources: set[str] = set()

    def _meta():
        for oid, cut in cuts.items():
            e = by_id[oid]
            e.pipeline_version = cut.version
            e.psf_fwhm_arcsec = _finite(cut.psf_fwhm_arcsec)
            e.variance_median = _finite(np.nanmedian(cut.variance)) if np.isfinite(cut.variance).any() else None
            try:
                from .science import flags as flagmod
                e.flag_counts = flagmod.flag_counts(cut.raw_flags, cut.flag_names)
            except Exception:  # noqa: BLE001
                e.flag_counts = None
            ra_e, dec_e = pos_at(cut.mjd)
            try:
                lam, bw, src = calib_cache.wavelength_at(cut, ra_e, dec_e, calib.get((cut.detector, cut.version)), exp=e)
            except Exception:  # noqa: BLE001
                lam, bw, src = (e.em_min_um + e.em_max_um) / 2, (e.em_max_um - e.em_min_um), "sia_band_center"
            e.wavelength_um, e.bandwidth_um = _finite(lam), _finite(bw)
            wl_sources.add(src)

    await anyio.to_thread.run_sync(_meta)
    inv.provenance.pipeline_versions = sorted({c.version for c in cuts.values() if c.version})

    # ---------------- stack + render
    await _emit(inv, progress_cb, "stack", 58, "Reprojecting and stacking visits")
    from .science import epochs, render
    from .science import difference as diffmod

    grid: GridSpec = epochs.make_grid(c_ra, c_dec, req.fov_arcmin)
    inv.grid = grid.to_model()
    visit_of = {(e.obs_id, e.detector): e.visit_id for e in inv.exposures}
    vmjd = {v.id: v.mjd_mean for v in visits}
    stacks: dict[tuple[str, object], Stack] = {}
    frames: list[Frame] = []
    fdir = inv_dir(inv_id) / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    base = f"/api/investigations/{inv_id}"
    diff_ctx: list[DiffContext] = []

    def _stack_render():
        groups: dict[tuple[str, object], list[CutoutData]] = defaultdict(list)
        for oid, cut in cuts.items():
            vid = visit_of[oid]
            groups[(vid, cut.detector)].append(cut)
            groups[(vid, "all")].append(cut)
        for key, cl in groups.items():
            try:
                stacks[key] = epochs.stack_cutouts(cl, grid)
            except Exception:  # noqa: BLE001
                log.exception("stack %s failed", key)
        dets: list[object] = sorted({k[1] for k in stacks if k[1] != "all"}) + ["all"]  # type: ignore[type-var]
        for det in dets:
            vids = sorted([k[0] for k in stacks if k[1] == det], key=lambda v: vmjd.get(v, 0))
            arrs = [stacks[(v, det)].S for v in vids]
            if not arrs:
                continue
            vmin, vmax = render.shared_stretch(arrs)
            stretch = Stretch(kind="asinh", vmin=float(vmin), vmax=float(vmax), unit="MJy/sr")
            for v in vids:
                st = stacks[(v, det)]
                fr = Frame(kind="visit_stack", visit_id=v, detector=det, url=f"{base}/frames/{v}/{det}.png",  # type: ignore[arg-type]
                           stretch=stretch, mjd=vmjd.get(v))
                render.to_png(st.S, vmin, vmax, frame_file(inv_id, fr))
                frames.append(fr)
                # flags overlay (union over members)
                try:
                    hard_u = np.zeros(grid.shape, bool)
                    cont_u = np.zeros(grid.shape, bool)
                    members = groups[(v, det)]
                    for cut in members:
                        h, c, _s = epochs.reproject_flags(cut, grid)
                        hard_u |= h
                        cont_u |= c
                    ff = Frame(kind="flags", visit_id=v, detector=det, url=f"{base}/flags/{v}/{det}.png", mjd=vmjd.get(v))  # type: ignore[arg-type]
                    render.flags_png(hard_u, cont_u, frame_file(inv_id, ff))
                    frames.append(ff)
                    st.contam = cont_u if st.contam is None else (st.contam | cont_u)
                except Exception:  # noqa: BLE001
                    log.exception("flags render failed")
            # single exposures (per detector only)
            if det != "all":
                for oid, cut in sorted(cuts.items(), key=lambda kv: kv[1].mjd):
                    if cut.detector != det:
                        continue
                    try:
                        I, _V, _m = epochs.reproject_cutout(cut, grid)
                        fr = Frame(kind="exposure", obs_id=oid[0], visit_id=visit_of[oid], detector=det,  # type: ignore[arg-type]
                                   url=f"{base}/exposures/{oid}/{det}.png", stretch=stretch, mjd=cut.mjd)
                        render.to_png(I, vmin, vmax, frame_file(inv_id, fr))
                        frames.append(fr)
                    except Exception:  # noqa: BLE001
                        log.exception("exposure render failed")
            # difference images: consecutive pairs + first→last
            pairs = list(zip(vids[:-1], vids[1:]))
            if len(vids) > 2:
                pairs.append((vids[0], vids[-1]))
            for a, b in pairs:
                sa, sb = stacks[(a, det)], stacks[(b, det)]
                for method in ("simple", "psf_matched"):
                    try:
                        fa = (sa.fwhm_arcsec or 0) / grid.pixscale_arcsec or None
                        fb = (sb.fwhm_arcsec or 0) / grid.pixscale_arcsec or None
                        dr = diffmod.zmap(sa, sb, method=method, fwhm_a_px=fa, fwhm_b_px=fb)
                        if dr.method != method:
                            continue  # PSF matching unavailable (no FWHM): don't mislabel a simple diff
                        fr = Frame(kind="diff", visit_id=a, visit_b=b, detector=det, method=method,  # type: ignore[arg-type]
                                   url=f"{base}/diff/{a}/{b}/{det}.png?method={method}",
                                   stretch=Stretch(kind="linear", vmin=-8, vmax=8, unit="sigma"), mjd=vmjd.get(b))
                        render.zmap_png(dr.Z, frame_file(inv_id, fr))
                        frames.append(fr)
                        if method == "simple" and det != "all":
                            contam = np.zeros(grid.shape, bool)
                            for s_ in (sa, sb):
                                if s_.contam is not None:
                                    contam |= s_.contam
                            good = (~sa.mask) & (~sb.mask)
                            diff_ctx.append(DiffContext(visit_a=a, visit_b=b, detector=int(det), mjd_a=vmjd[a],  # type: ignore[arg-type]
                                                        mjd_b=vmjd[b], diff=dr, contam=contam, good=good))
                    except Exception:  # noqa: BLE001
                        log.exception("diff %s %s %s %s failed", a, b, det, method)

    await anyio.to_thread.run_sync(_stack_render)
    inv.frames = frames
    await _emit(inv, progress_cb, "render", 70, f"Rendered {len(frames)} frames")

    # ---------------- track
    sel_ok = [e for e in inv.exposures if (e.obs_id, e.detector) in cuts]
    if has_pm:
        tr = ephemeris.predict_track(target, [e.mjd for e in sel_ok])
    else:
        tr = [(target.ra, target.dec)] * len(sel_ok)
    track = []
    pred: dict[tuple[str, int], tuple[float, float]] = {}
    for e, (ra_t, dec_t) in zip(sel_ok, tr):
        pred[(e.obs_id, e.detector)] = (ra_t, dec_t)
        x, y = grid.wcs.world_to_pixel_values(ra_t, dec_t)
        track.append(TrackPoint(mjd=e.mjd, ra=ra_t, dec=dec_t, x=float(x), y=float(y), obs_id=e.obs_id))
    inv.track = track

    # ---------------- measure
    await _emit(inv, progress_cb, "measure", 72, "Photometry, spectrum, light curve, astrometry")
    from .science import astrometry as astro
    from .science import lightcurve, photometry, spectrum

    def _measure():
        phot: list[PhotPoint] = []
        for e in sel_ok:
            cut = cuts[(e.obs_id, e.detector)]
            ra_t, dec_t = pred[(e.obs_id, e.detector)]
            epsf = None
            try:
                cp = calib.get((cut.detector, cut.version))
                if cp is not None:
                    px, py = cut.wcs.world_to_pixel_values(ra_t, dec_t)
                    epsf = calib_cache.load_epsf(cp, *calib_cache.detector_xy(cut, float(px), float(py)))
            except Exception:  # noqa: BLE001
                epsf = None
            try:
                r = photometry.measure(cut.image, cut.variance, cut.raw_flags, cut.hard, cut.wcs, ra_t, dec_t,
                                       cut.psf_fwhm_arcsec, cut.flag_names, epsf=epsf)
            except Exception:  # noqa: BLE001
                log.exception("photometry failed for %s", e.obs_id)
                continue
            gx, gy = grid.wcs.world_to_pixel_values(ra_t, dec_t)
            phot.append(PhotPoint(
                obs_id=e.obs_id, visit_id=e.visit_id, detector=e.detector, mjd=cut.mjd,
                wavelength_um=e.wavelength_um or (e.em_min_um + e.em_max_um) / 2,
                bandwidth_um=e.bandwidth_um or (e.em_max_um - e.em_min_um),
                flux_ujy=_finite(r.flux_ujy) if not r.rejected else None,
                flux_err_ujy=_finite(r.flux_err_ujy) if not r.rejected else None,
                ab_mag=_finite(r.ab_mag) if not r.rejected else None, snr=_finite(r.snr) if not r.rejected else None,
                saturated=bool(r.saturated), flagged_frac=float(r.flagged_frac),
                contamination_bits=list(r.contamination_bits), apcorr=float(r.apcorr or 1.0),
                apcorr_method=r.apcorr_method if r.apcorr_method in ("epsf", "gaussian") else "gaussian",  # type: ignore[arg-type]
                x=float(gx), y=float(gy)))
        lc, phot = lightcurve.metrics(phot, visits)
        spec = spectrum.build_spectrum(
            phot, wavelength_source="sia_band_center" if wl_sources == {"sia_band_center"} else "wcs_wave")

        # detection SNR on stacks at the predicted visit position
        snr_best = None
        for (vid, det), st in stacks.items():
            ra_v, dec_v = pos_at(vmjd.get(vid, mean_mjd))
            fwhm_px = max(1.0, (st.fwhm_arcsec or 6.5) / grid.pixscale_arcsec)
            try:
                s = photometry.forced_snr_on_stack(st.S, st.V, grid.wcs, ra_v, dec_v, fwhm_px)
            except Exception:  # noqa: BLE001
                s = None
            if s is not None and math.isfinite(s) and (snr_best is None or s > snr_best):
                snr_best = s

        # astrometry: per visit, best unsaturated stack (all-IR or single detector) by centroid SNR
        sat_by_visit: dict[str, float] = {}
        for v in visits:
            pv = [p for p in phot if p.visit_id == v.id]
            sat_by_visit[v.id] = (sum(p.saturated for p in pv) / len(pv)) if pv else 0.0
        measured: list[AstrometryMeasured] = []
        for v in visits:
            ra_v, dec_v = pos_at(v.mjd_mean)
            best = None
            for (vid, det), st in stacks.items():
                if vid != v.id:
                    continue
                if det != "all":
                    pv = [p for p in phot if p.visit_id == v.id and p.detector == det]
                    if pv and any(p.saturated for p in pv):
                        continue
                elif sat_by_visit.get(v.id, 0) > 0.5:
                    continue
                fwhm_px = max(1.0, (st.fwhm_arcsec or 6.5) / grid.pixscale_arcsec)
                try:
                    c = astro.centroid(st.S, st.V, grid.wcs, ra_v, dec_v, fwhm_px)
                except Exception:  # noqa: BLE001
                    c = None
                if c is not None and (best is None or c.snr > best[1].snr):
                    best = (det, c)
            if best is not None:
                det, c = best
                measured.append(AstrometryMeasured(
                    visit_id=v.id, mjd=v.mjd_mean, ra=c.ra, dec=c.dec, err_arcsec=c.err_arcsec, snr=c.snr,
                    detector=det, crowded=bool(c.crowded), saturated=bool(c.saturated or sat_by_visit.get(v.id, 0) > 0.5)))
        try:
            measured = astro.residuals(measured, target) if has_pm else measured
        except Exception:  # noqa: BLE001
            log.exception("residuals failed")
        fit = None
        try:
            fit = astro.fit_pm(measured, target) if measured else None
        except Exception:  # noqa: BLE001
            log.exception("fit_pm failed")
        return phot, lc, spec, snr_best, measured, fit, sat_by_visit

    phot, lc, spec, snr_best, measured, fit, sat_by_visit = await anyio.to_thread.run_sync(_measure)
    inv.photometry, inv.lightcurve, inv.spectrum = phot, lc, spec
    astrometry = Astrometry(measured=measured, fit=fit)
    if has_pm and target.parallax is not None:
        astrometry.catalog = AstrometryCatalog(pm_ra=target.pm_ra, pm_dec=target.pm_dec, parallax=target.parallax,  # type: ignore[arg-type]
                                               source=target.source)
    if fit is not None and astrometry.catalog is not None:
        sa = max(fit.pm_ra_err, 1e-6)
        sd = max(fit.pm_dec_err, 1e-6)
        astrometry.consistency_sigma = float(max(abs(fit.pm_ra - astrometry.catalog.pm_ra) / sa,
                                                 abs(fit.pm_dec - astrometry.catalog.pm_dec) / sd))
    inv.astrometry = astrometry
    await _emit(inv, progress_cb, "crossmatch", 82, "Querying Gaia, SIMBAD, CatWISE, SkyBoT")

    # ---------------- crossmatch (one field cone, then local association)
    half_diag = req.fov_arcmin * 60 / 2 * 1.42
    field_r = float(min(180.0, max(30.0, half_diag)))
    xm_field = await crossmatch.crossmatch_all(c_ra, c_dec, field_r, mean_mjd)
    for svc in ("gaia", "simbad", "catwise", "skybot"):
        services[svc] = getattr(xm_field, svc).status
    inv.crossmatch = _restrict(xm_field, c_ra, c_dec, 30.0)
    bright = None
    try:
        bright = await crossmatch.bright_stars(c_ra, c_dec, 2.0, 8.0)
    except Exception:  # noqa: BLE001
        bright = None
    try:
        first_v = next((v for v in visits if (v.id, "all") in stacks), None)
        if first_v is not None:
            first_all = stacks[(first_v.id, "all")]
            # propagate to the epoch of the image being measured; skip stars near the target (its own halo/bloom)
            t_ra, t_dec = pos_at(first_v.mjd_mean)
            gstars = [s for s in await crossmatch.gaia_field(c_ra, c_dec, field_r, first_v.mjd_mean)
                      if _sep_arcsec(s.ra, s.dec, t_ra, t_dec) > 30.0]
            if gstars:
                fwhm_px = max(1.0, (first_all.fwhm_arcsec or 6.5) / grid.pixscale_arcsec)
                inv.astrometry.registration = await anyio.to_thread.run_sync(
                    lambda: astro.registration_check(first_all.S, grid.wcs, gstars, fwhm_px))
    except Exception:  # noqa: BLE001
        log.exception("registration check failed")

    # ---------------- blend check: a Gaia neighbour within ~1 PSF FWHM of the predicted target position
    # cannot be separated at SPHEREx resolution (6.2"/px); its light biases the centroid and the
    # short-wavelength photometry. Such visits are excluded from the PM fit and the track comparison.
    if measured and xm_field.gaia.status == "ok":
        fwhms = [st.fwhm_arcsec for st in stacks.values() if st.fwhm_arcsec]
        blend_r = float(np.median(fwhms)) if fwhms else 6.5
        blended: dict[str, tuple[str, float, Optional[float]]] = {}
        upd = []
        for m in measured:
            p_ra, p_dec = pos_at(m.mjd)
            near = []
            for g in xm_field.gaia.matches:
                # Gaia positions are at mean_mjd; move each star to this visit with its own PM
                g_ra, g_dec = g.ra, g.dec
                if g.pm_ra is not None and g.pm_dec is not None:
                    dt = (m.mjd - mean_mjd) / 365.25
                    g_dec = g.dec + g.pm_dec * dt / 3.6e6
                    g_ra = g.ra + g.pm_ra * dt / 3.6e6 / max(math.cos(math.radians(g.dec)), 1e-6)
                d_pred = _sep_arcsec(g_ra, g_dec, p_ra, p_dec)
                if d_pred <= 2.0:
                    continue  # the target's own Gaia entry
                d_meas = _sep_arcsec(g_ra, g_dec, m.ra, m.dec)
                d_m_pred = _sep_arcsec(m.ra, m.dec, p_ra, p_dec)
                # (a) neighbour within ~1 FWHM of where the target should be, or
                # (b) the centroid sits on the neighbour (within FWHM/2) rather than on the prediction
                if d_pred <= blend_r or (d_meas <= 0.5 * blend_r and d_meas < d_m_pred):
                    near.append((d_pred, g))
            near.sort(key=lambda t: t[0])
            nb = near[0] if near else None
            if nb is not None:
                blended[m.visit_id] = (nb[1].id, nb[0], nb[1].mag)
                m = m.model_copy(update={"crowded": True})
            upd.append(m)
        if blended:
            measured = upd
            inv.astrometry.measured = measured
            try:
                fit = astro.fit_pm(measured, target)
            except Exception:  # noqa: BLE001
                log.exception("fit_pm (after blend check) failed")
                fit = None
            inv.astrometry.fit = fit
            inv.astrometry.consistency_sigma = None
            if fit is not None and inv.astrometry.catalog is not None:
                inv.astrometry.consistency_sigma = float(max(
                    abs(fit.pm_ra - inv.astrometry.catalog.pm_ra) / max(fit.pm_ra_err, 1e-6),
                    abs(fit.pm_dec - inv.astrometry.catalog.pm_dec) / max(fit.pm_dec_err, 1e-6)))
            gid, d, gmag = next(iter(blended.values()))
            mag_txt = f", G = {gmag:.1f}" if gmag is not None else ""
            inv.warnings.append(
                f"Possible blend: {gid}{mag_txt} lies {d:.1f}\" from the predicted target position (PSF FWHM ≈ {blend_r:.1f}\"), "
                f"or the measured centroid falls on it, in {len(blended)} of {len(measured)} visit(s). Centroids from those visits are excluded from the motion fit, "
                "and short-wavelength fluxes and light-curve changes may include the neighbour's light.")

    # ---------------- candidates
    await _emit(inv, progress_cb, "score", 90, "Field change candidates and evidence")
    from .science import candidates as candmod
    from .science import scoring

    max_pm = 10000.0
    try:
        raws = await anyio.to_thread.run_sync(lambda: candmod.find_candidates(diff_ctx, grid, max_pm))
    except Exception:  # noqa: BLE001
        log.exception("candidates failed")
        raws = []
    n_vis = len(visits)
    cands: list[Candidate] = []
    for rc in raws:
        cxm = _restrict(xm_field, rc.ra, rc.dec, None)
        nearest_bright = _nearest_bright(bright, rc.ra, rc.dec)
        ev = scoring.build_evidence(EvidenceInput(
            subject="candidate", snr=float(abs(rc.peak_z)), n_visits=n_vis, recurrence=rc.recurrence,
            contamination=list(rc.contamination_near), bright_neighbor_arcmin=nearest_bright, crossmatch=cxm,
            motion_sig=None, name=rc.id,
            provenance={"recurrence": [f"{a}→{b}" for a, b in rc.visit_pairs]}))
        thumbs = []
        for vid in sorted({v for pair in rc.visit_pairs for v in pair}, key=lambda v: vmjd.get(v, 0)):
            det = rc.detectors[0] if rc.detectors else "all"
            st = stacks.get((vid, det))
            if st is None:
                continue
            try:
                _write_thumb(st, rc.x, rc.y, thumb_file(inv_id, rc.id, vid), render, stacks, vid, det)
                thumbs.append(Thumbnail(visit_id=vid, url=f"{base}/thumbs/{rc.id}/{vid}.png"))
            except Exception:  # noqa: BLE001
                log.exception("thumb failed")
        cands.append(Candidate(
            id=rc.id, ra=rc.ra, dec=rc.dec, x=rc.x, y=rc.y, kind=rc.kind, peak_z=float(rc.peak_z),  # type: ignore[arg-type]
            motion=CandidateMotion(pm_ra=rc.pm_ra, pm_dec=rc.pm_dec) if rc.pm_ra is not None and rc.pm_dec is not None else None,
            detectors=rc.detectors, visit_pairs=rc.visit_pairs, crossmatch=cxm, evidence=ev, thumbnails=thumbs))
    inv.candidates = cands

    # ---------------- target evidence
    usable = [p for p in phot if p.flux_ujy is not None or p.saturated]
    n_visits_data = len({p.visit_id for p in usable})
    sat_frac = (sum(p.saturated for p in phot) / len(phot)) if phot else None
    flagged = float(np.median([p.flagged_frac for p in phot])) if phot else None
    contam = sorted({b for p in phot for b in p.contamination_bits})
    motion_sig = None
    if fit is not None:
        mu = math.hypot(fit.pm_ra, fit.pm_dec)
        smu = math.hypot(fit.pm_ra * fit.pm_ra_err, fit.pm_dec * fit.pm_dec_err) / mu if mu > 0 else None
        motion_sig = mu / smu if smu else None
    track_agree = None
    rs = [math.hypot(m.resid_ra_arcsec or 0, m.resid_dec_arcsec or 0) / max(m.err_arcsec, 1e-3)
          for m in measured if m.resid_ra_arcsec is not None and not m.crowded]
    if rs:
        track_agree = float(np.median(rs))
    sig_dets = sum(1 for m in lc.metrics if m.significant)
    chi2s = [m.chi2_red for m in lc.metrics if m.chi2_red is not None]
    amps = [m.amp_sigma for m in lc.metrics if m.amp_sigma is not None]
    ident = inv.crossmatch
    cat_pm, cat_var = _catalog_pm_and_var(ident, c_ra, c_dec)
    if has_pm and cat_pm is None:
        cat_pm = math.hypot(target.pm_ra or 0, target.pm_dec or 0)
    if target.otype:  # SIMBAD code (resolver) or descriptive text (built-ins, e.g. "Mira variable")
        ot = target.otype.strip()
        if ot in VARIABLE_OTYPES or any(w in ot.lower() for w in ("variable", "mira", "t tauri")):
            cat_var = True
    inv.evidence = scoring.build_evidence(EvidenceInput(
        subject="target", snr=snr_best, n_visits=n_visits_data, motion_sig=motion_sig,
        pm_measured=(fit.pm_ra, fit.pm_dec) if fit else None,
        catalog_pm_consistency=inv.astrometry.consistency_sigma, track_agreement=track_agree,
        variability_significant_dets=sig_dets, max_chi2_red=max(chi2s) if chi2s else None,
        amp_sigma=max(amps) if amps else None, coherent_detectors=lc.coherent_detectors, recurrence=None,
        flagged_frac=flagged, saturated_frac=sat_frac, contamination=contam,
        bright_neighbor_arcmin=_nearest_bright(bright, c_ra, c_dec, exclude_arcsec=10.0), crossmatch=ident,
        catalog_pm_total=cat_pm, catalog_variable=cat_var, name=target.name,
        provenance={"detection_snr": [f"{k[0]}:{k[1]}" for k in stacks][:12],
                    "photometry": [p.obs_id for p in phot][:40]}))

    # ---------------- warnings + provenance
    if sat_frac is not None and sat_frac > 0.2:
        inv.warnings.append(f"Target saturated in {round(100 * sat_frac)}% of exposures: fluxes there are lower limits.")
    if snr_best is not None and snr_best < 5:
        inv.warnings.append(f"Target only marginally detected in the stacks (best S/N {snr_best:.1f}).")
    if S.cutout_mode == "stream":
        pass  # documented in methods
    for svc in ("gaia", "simbad", "catwise", "skybot"):
        st = services.get(svc)
        if st and st != "ok":
            label = {"gaia": "Gaia DR3", "simbad": "SIMBAD", "catwise": "CatWISE2020", "skybot": "SkyBoT"}[svc]
            inv.warnings.append(f"{label} could not be queried ({st}); evidence that depends on it is marked unavailable.")
    inv.provenance.services = {k: (v if v in ("ok", "unavailable", "error") else "error") for k, v in services.items()}  # type: ignore[assignment]
    inv.provenance.generated_at = now_iso()
    inv.progress = Progress(stage="done", pct=100, message="Done")
    inv.status = "done"
    return inv


# ---------------------------------------------------------------- small helpers
def _restrict(xm: CrossMatch, ra: float, dec: float, radius_arcsec: Optional[float]) -> CrossMatch:
    """Recompute separations from (ra, dec); keep within radius (None = identity radii per service)."""
    out = {}
    for svc in ("gaia", "simbad", "catwise", "skybot"):
        cr: CatalogResult = getattr(xm, svc)
        r = radius_arcsec if radius_arcsec is not None else IDENTITY_RADIUS[svc]
        ms = []
        for m in cr.matches:
            sep = _sep_arcsec(ra, dec, m.ra, m.dec)
            if sep <= r:
                mm = m.model_copy()
                mm.sep_arcsec = round(sep, 3)
                ms.append(mm)
        ms.sort(key=lambda m: m.sep_arcsec)
        out[svc] = CatalogResult(service=svc, status=cr.status, message=cr.message, matches=ms[:25])  # type: ignore[arg-type]
    return CrossMatch(**out)


def _catalog_pm_and_var(xm: CrossMatch, ra: float, dec: float) -> tuple[Optional[float], bool]:
    pm = None
    var = False
    for svc in ("gaia", "simbad", "catwise"):
        for m in getattr(xm, svc).matches:
            if m.sep_arcsec <= IDENTITY_RADIUS[svc]:
                if pm is None and m.pm_ra is not None and m.pm_dec is not None:
                    pm = math.hypot(m.pm_ra, m.pm_dec)
                if (m.variable_flag or "").upper() == "VARIABLE":
                    var = True
                if m.otype and m.otype in VARIABLE_OTYPES:
                    var = True
    return pm, var


def _nearest_bright(bright: Optional[list[CatalogMatch]], ra: float, dec: float, exclude_arcsec: float = 0.0):
    if bright is None:
        return None
    seps = [_sep_arcsec(ra, dec, b.ra, b.dec) for b in bright]
    seps = [s for s in seps if s > exclude_arcsec]
    return (min(seps) / 60.0) if seps else float("inf")


def _write_thumb(st: Stack, x: float, y: float, path: Path, render, stacks, vid, det) -> None:
    half = 7
    ny, nx = st.S.shape
    xi, yi = int(round(x)), int(round(y))
    x0, x1 = max(0, xi - half), min(nx, xi + half + 1)
    y0, y1 = max(0, yi - half), min(ny, yi + half + 1)
    cut = st.S[y0:y1, x0:x1]
    # stretch shared across the candidate's visits on the same detector
    arrs = [s.S[y0:y1, x0:x1] for (v, d), s in stacks.items() if d == det]
    vmin, vmax = render.shared_stretch(arrs)
    render.to_png(cut, vmin, vmax, path)
