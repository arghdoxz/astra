"use client";

/**
 * Landing-page plate: the real Eps Ind B all-IR visit stacks from the saved
 * demo bundle, blinked like a comparator, with the predicted track and the
 * measured proper motion read from the same bundle. Nothing here is simulated.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Investigation } from "@/lib/types";

const SLUG = "eps-ind-b";

export default function BlinkPlate() {
  const [inv, setInv] = useState<Investigation | null>(null);
  const [i, setI] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch(`/demo/${SLUG}/investigation.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d: Investigation) => alive && setInv(d))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, []);

  const visits = inv?.visits ?? [];
  const n = visits.length;
  useEffect(() => {
    if (n < 2) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = setInterval(() => setI((k) => (k + 1) % n), 900);
    return () => clearInterval(id);
  }, [n]);

  if (failed) return null;
  if (!inv || !inv.grid || n === 0) {
    return <div className="card frame aspect-square w-full animate-pulse" aria-hidden />;
  }

  const g = inv.grid;
  const v = visits[i];
  const track = inv.track ?? [];
  const yOf = (y: number) => g.height - 1 - y + 0.5;
  const xOf = (x: number) => x + 0.5;
  const nearest = (mjd: number) => track.reduce((b, p) => (Math.abs(p.mjd - mjd) < Math.abs(b.mjd - mjd) ? p : b), track[0]);
  const marks = visits.map((vv) => (track.length ? nearest(vv.mjd_mean) : null));
  const fit = inv.astrometry?.fit ?? null;
  const fmt = (x: number) => Math.round(x).toLocaleString("en-US");

  return (
    <figure className="card frame p-3">
      <div className="relative aspect-square w-full overflow-hidden bg-black">
        {visits.map((vv, k) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={vv.id}
            src={`/demo/${SLUG}/frames/stack_${vv.id}_all.png`}
            alt={k === i ? `SPHEREx all-IR stack of Eps Ind B, visit ${vv.date_label}` : ""}
            className="absolute inset-0 h-full w-full"
            style={{ imageRendering: "pixelated", opacity: k === i ? 1 : 0 }}
          />
        ))}
        <svg viewBox={`0 0 ${g.width} ${g.height}`} className="absolute inset-0 h-full w-full" aria-hidden>
          {track.length > 1 && (
            <polyline
              points={track.map((p) => `${xOf(p.x)},${yOf(p.y)}`).join(" ")}
              fill="none"
              stroke="#ffb547"
              strokeOpacity="0.6"
              strokeWidth="0.12"
              strokeDasharray="0.4 0.35"
            />
          )}
          {marks.map((p, k) =>
            p ? (
              <circle key={k} cx={xOf(p.x)} cy={yOf(p.y)} r={k === i ? 1.6 : 0.25} fill="none" stroke="#ffb547" strokeWidth={k === i ? 0.14 : 0.1} strokeOpacity={k === i ? 0.95 : 0.5} />
            ) : null,
          )}
        </svg>
        <div className="mono absolute left-2 top-2 bg-black/70 px-1.5 py-0.5 text-[0.68rem] tracking-wider text-fg">
          VISIT {i + 1}/{n} · {v.date_label}
        </div>
        <div className="mono absolute bottom-2 right-2 bg-black/70 px-1.5 py-0.5 text-[0.62rem] tracking-wider text-muted">
          N↑ E← · {g.cdelt_arcsec.toFixed(2)}″/px
        </div>
      </div>
      <figcaption className="mt-3 space-y-2">
        <div className="flex items-baseline justify-between gap-3">
          <span className="font-[family-name:var(--font-display)] text-lg font-semibold">Eps Indi B</span>
          <span className="chip chip-green">real SPHEREx data</span>
        </div>
        <dl className="mono grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-[0.72rem]">
          <dt className="text-muted">frames</dt>
          <dd>all-IR visit stacks, 0.75–5 µm</dd>
          {fit && (
            <>
              <dt className="text-muted">µ measured</dt>
              <dd>
                {fmt(fit.pm_ra)} ± {fmt(fit.pm_ra_err)}, {fmt(fit.pm_dec)} ± {fmt(fit.pm_dec_err)} mas/yr
              </dd>
            </>
          )}
          <dt className="text-muted">dashed line</dt>
          <dd>position predicted from the Gaia motion</dd>
        </dl>
        <Link href={`/investigate?ra=331.04415&dec=-56.78284&name=Eps%20Ind%20B`} className="mono inline-block text-[0.72rem] uppercase tracking-[0.12em]">
          Open this investigation →
        </Link>
      </figcaption>
    </figure>
  );
}
