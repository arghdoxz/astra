"""Precompute static demo bundles for the five demo targets.

Run from backend/:
    uv run python -m scripts.precompute_targets [--only slug] [--fov 3] [--max-exposures N]

Runs the real pipeline (network: IRSA, Gaia, SIMBAD). Failed investigations never produce a
bundle; nothing is fabricated. Output: frontend/public/demo/{slug}/ and demo/index.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from app.models import Investigation, InvestigationRequest
from app.pipeline import frame_file, inv_dir, run_investigation

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / "frontend" / "public" / "demo"
MAX_EXPOSURE_FRAMES = 120

# ICRS J2000 positions from docs/SCIENCE_REFERENCE.md section 4. The pipeline propagates proper
# motion to the SPHEREx epoch when propagate_pm=True, so WISE 0855 is centred on its propagated
# position (the bundle is centred by the pipeline, not by this script).
TARGETS: dict[str, dict] = {
    "barnard": {"name": "Barnard's Star", "ra": 269.45208, "dec": 4.69336},
    "eps-ind-b": {"name": "Eps Ind B", "ra": 331.04415, "dec": -56.78284},
    "wise-0855": {"name": "WISE 0855-0714", "ra": 133.81891, "dec": -7.24705},
    "rw-aur": {"name": "RW Aur", "ra": 76.95653, "dec": 30.40144},
    "r-dra": {"name": "R Dra", "ra": 248.16761, "dec": 66.75498},
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _progress_printer(slug: str):
    last: dict = {"key": None}

    async def cb(inv: Investigation) -> None:
        p = inv.progress
        key = (p.stage, int(p.pct // 10))
        if key != last["key"]:
            last["key"] = key
            print(f"  [{slug}] {p.stage:<10} {p.pct:5.1f}%  {p.message}", flush=True)

    return cb


def _find_thumbnail(inv_id: str, cand_id: str, visit_id: str, url: str) -> Path | None:
    root = inv_dir(inv_id)
    base = Path(url.split("?")[0]).name
    if base:
        for name in {base, base if base.endswith(".png") else base + ".png"}:
            hits = [p for p in root.rglob(name) if p.is_file()]
            if hits:
                return hits[0]
    for p in root.rglob("*.png"):
        if cand_id in p.name and visit_id in p.name:
            return p
    return None


def _dir_size_mb(d: Path) -> float:
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1e6


def _write_bundle(slug: str, inv: Investigation) -> float:
    out = DEMO_DIR / slug
    frames_out = out / "frames"
    if frames_out.exists():
        shutil.rmtree(frames_out)
    frames_out.mkdir(parents=True, exist_ok=True)
    local_id = inv.id  # where the PNGs live (cache/inv/{id}/)

    kept = []
    n_exp = 0
    omitted_exp = 0
    for fr in inv.frames:
        if fr.kind == "exposure" and n_exp >= MAX_EXPOSURE_FRAMES:
            omitted_exp += 1
            continue
        src = frame_file(local_id, fr)
        if not src.is_file():
            inv.warnings.append(f"Frame {src.name} was missing on disk and is omitted from the bundle.")
            continue
        shutil.copy2(src, frames_out / src.name)
        fr.url = f"frames/{src.name}"
        if fr.kind == "exposure":
            n_exp += 1
        kept.append(fr)
    inv.frames = kept
    if omitted_exp:
        inv.warnings.append(
            f"This static demo bundle omits {omitted_exp} single-exposure frames "
            f"(kept the first {MAX_EXPOSURE_FRAMES}); the live investigation has them all."
        )

    for cand in inv.candidates:
        thumbs = []
        for th in cand.thumbnails:
            src = _find_thumbnail(local_id, cand.id, th.visit_id, th.url)
            if src is None:
                inv.warnings.append(f"Thumbnail for candidate {cand.id} / {th.visit_id} not found; omitted.")
                continue
            name = f"thumb_{cand.id}_{th.visit_id}.png"
            shutil.copy2(src, frames_out / name)
            th.url = f"frames/{name}"
            thumbs.append(th)
        cand.thumbnails = thumbs

    inv.id = f"demo_{slug}"
    inv.generated_from = "demo_bundle"
    (out / "investigation.json").write_text(
        json.dumps(inv.model_dump(mode="json", by_alias=True), indent=1), encoding="utf-8"
    )
    return _dir_size_mb(out)


def _update_index(entries: list[dict]) -> None:
    path = DEMO_DIR / "index.json"
    existing: list = []
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    by_slug = {e["slug"]: e for e in existing if isinstance(e, dict) and "slug" in e}
    for e in entries:
        by_slug[e["slug"]] = e
    order = list(TARGETS) + [s for s in by_slug if s not in TARGETS]
    merged = [by_slug[s] for s in order if s in by_slug]
    path.write_text(json.dumps(merged, indent=2), encoding="utf-8")


async def _run_one(slug: str, fov: float, max_exp: int) -> dict:
    t = TARGETS[slug]
    row: dict = {"slug": slug, "status": "error", "n_exp": "-", "visits": "-", "cls": "-", "conf": "-", "mb": "-"}
    req = InvestigationRequest(
        ra=t["ra"], dec=t["dec"], fov_arcmin=fov, name=t["name"],
        max_exposures=max_exp, detectors=[1, 2, 3, 4, 5, 6], propagate_pm=True,
    )
    print(f"== {slug}: {t['name']} (fov {fov}', max_exposures {max_exp})", flush=True)
    t0 = time.time()
    try:
        inv = await run_investigation(f"demo_{slug}", req, progress_cb=_progress_printer(slug))
    except Exception as exc:  # noqa: BLE001
        print(f"  [{slug}] FAILED: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        row["status"] = f"error: {type(exc).__name__}"
        return row
    if inv.status != "done":
        msg = inv.error.message if inv.error else "unknown"
        print(f"  [{slug}] investigation ended with status={inv.status}: {msg}", file=sys.stderr)
        row["status"] = f"{inv.status}: {msg[:40]}"
        return row

    row.update(
        n_exp=inv.provenance.n_exposures_used,
        visits=len(inv.visits),
        cls=inv.evidence.classification,
        conf=inv.evidence.confidence,
    )
    ra, dec = t["ra"], t["dec"]  # library (J2000) coordinates: what URLs and the offline fallback match against
    generated_at = inv.provenance.generated_at or _now()
    try:
        row["mb"] = f"{_write_bundle(slug, inv):.1f}"
    except Exception as exc:  # noqa: BLE001
        print(f"  [{slug}] bundle write failed: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        row["status"] = f"bundle_error: {type(exc).__name__}"
        return row
    row["status"] = "done"
    row["index"] = {
        "slug": slug,
        "name": t["name"],
        "ra": ra,
        "dec": dec,
        "fov_arcmin": fov,
        "generated_at": generated_at,
        "status": "done",
    }
    print(f"  [{slug}] done in {time.time() - t0:.0f}s", flush=True)
    return row


async def _main(args: argparse.Namespace) -> int:
    slugs = [args.only] if args.only else list(TARGETS)
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for slug in slugs:  # sequential: protects IRSA and the CPU
        rows.append(await _run_one(slug, args.fov, args.max_exposures))
    entries = [r["index"] for r in rows if "index" in r]
    if entries:
        _update_index(entries)

    print("\nslug        status                n_exp  visits  classification        confidence    MB")
    for r in rows:
        print(f"{r['slug']:<11} {str(r['status']):<21} {str(r['n_exp']):>5}  {str(r['visits']):>6}  "
              f"{str(r['cls']):<20}  {str(r['conf']):<12} {str(r['mb']):>5}")
    return 0 if all(r["status"] == "done" for r in rows) else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=list(TARGETS), help="run a single target")
    ap.add_argument("--fov", type=float, default=3.0, help="field of view in arcmin (default 3)")
    ap.add_argument("--max-exposures", type=int, default=160, help="max exposures per investigation (default 160)")
    args = ap.parse_args()
    sys.exit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
