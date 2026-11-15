"use client";

/**
 * Landing-page plate: the real Eps Ind B all-IR visit stacks from the saved demo bundle,
 * shown as a negative and blinked like a comparator, with the catalogue track and the
 * measured positions marked in red pencil. The proper motion printed underneath is read
 * from the same bundle. Nothing here is simulated.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Investigation } from "@/lib/types";

const SLUG = "eps-ind-b";
const PENCIL = "#b42d1c";

export default function BlinkPlate() {
  const [inv, setInv] = useState<Investigation | null>(null);
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
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
    if (n < 2 || paused) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = setInterval(() => setI((k) => (k + 1) % n), 900);
    return () => clearInterval(id);
  }, [n, paused]);

  if (failed) return null;
  if (!inv || !inv.grid || n === 0) {
    return <div className="card aspect-square w-full" aria-hidden />;
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
  const first = visits[0]?.date_label;
  const last = visits[n - 1]?.date_label;

  return (
    <figure className="card p-3 sm:p-4">
      {/* Plate envelope label */}
      <figcaption className="mono mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-fg pb-2 text-sm">
        <span className="font-bold">Plate A-0418 · Eps Indi B</span>
        <span className="text-muted">
          SPHEREx DR1 + QR3 · {first} to {last}
        </span>
      </figcaption>

      <button
        type="button"
        onClick={() => setPaused((p) => !p)}
        className="relative block aspect-square w-full cursor-pointer overflow-hidden bg-[#eef0ee]"
        aria-label={paused ? "Resume blinking the visits" : "Pause blinking on this visit"}
      >
        {visits.map((vv, k) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={vv.id}
            src={`/demo/${SLUG}/frames/stack_${vv.id}_all.png`}
            alt={k === i ? `SPHEREx all-infrared stack of Eps Indi B, visit ${vv.date_label}, shown as a negative` : ""}
            className="negative absolute inset-0 h-full w-full"
            style={{ imageRendering: "pixelated", opacity: k === i ? 1 : 0 }}
          />
        ))}
        <svg viewBox={`0 0 ${g.width} ${g.height}`} className="absolute inset-0 h-full w-full" aria-hidden>
          {track.length > 1 && (
            <polyline
              points={track.map((p) => `${xOf(p.x)},${yOf(p.y)}`).join(" ")}
              fill="none"
              stroke={PENCIL}
              strokeOpacity="0.75"
              strokeWidth="0.14"
              strokeLinecap="round"
              strokeDasharray="0.45 0.4"
            />
          )}
          {marks.map((p, k) =>
            p ? (
              k === i ? (
                <g key={k} fill="none" stroke={PENCIL} strokeLinecap="round">
                  <ellipse cx={xOf(p.x)} cy={yOf(p.y)} rx={1.7} ry={1.55} strokeWidth={0.2} transform={`rotate(18 ${xOf(p.x)} ${yOf(p.y)})`} />
                  <ellipse cx={xOf(p.x) + 0.08} cy={yOf(p.y) - 0.05} rx={1.78} ry={1.6} strokeWidth={0.09} strokeOpacity={0.7} />
                </g>
              ) : (
                <circle key={k} cx={xOf(p.x)} cy={yOf(p.y)} r={0.22} fill={PENCIL} fillOpacity={0.7} />
              )
            ) : null,
          )}
        </svg>
        <span className="mono absolute left-2 top-2 border border-fg bg-panel px-1.5 text-sm text-fg">
          Visit {i + 1} of {n} · {v.date_label}
          {paused ? " · paused" : ""}
        </span>
        <span className="mono absolute bottom-2 right-2 bg-panel px-1.5 text-xs text-muted">
          N up, E left · {g.cdelt_arcsec.toFixed(2)}″ per pixel
        </span>
      </button>

      <div className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-[1fr_auto] sm:items-end">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted">Shown</dt>
          <dd>All-infrared visit stacks, 0.75 to 5 µm, as a negative</dd>
          {fit && (
            <>
              <dt className="text-muted">Measured motion</dt>
              <dd className="mono">
                {fmt(fit.pm_ra)} ± {fmt(fit.pm_ra_err)}, {fmt(fit.pm_dec)} ± {fmt(fit.pm_dec_err)} mas/yr
              </dd>
            </>
          )}
          <dt className="text-muted">Dashed line</dt>
          <dd>Where Gaia&rsquo;s motion says it should be</dd>
        </dl>
        <Link href={`/investigate?ra=331.04415&dec=-56.78284&name=Eps%20Ind%20B`} className="text-[0.95rem] font-semibold">
          Open this plate
        </Link>
      </div>
    </figure>
  );
}
