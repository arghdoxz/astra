"use client";

import { useMemo } from "react";
import type { Investigation, TrackPoint } from "@/lib/types";
import { visitColor } from "@/components/plots/plotTheme";
import { Card, EmptyState, Note, SectionTitle, TableWrap, mjdToDate, num, tdCls, thCls } from "./shared";

const W = 380;
const H = 340;
const M = { l: 46, r: 14, t: 12, b: 42 };

function offsetArcsec(ra: number, dec: number, ra0: number, dec0: number): [number, number] {
  const dra = ((((ra - ra0) % 360) + 540) % 360) - 180;
  return [dra * Math.cos((dec0 * Math.PI) / 180) * 3600, (dec - dec0) * 3600];
}

function interpTrack(track: TrackPoint[], mjd: number): TrackPoint | null {
  if (track.length === 0) return null;
  const s = [...track].sort((a, b) => a.mjd - b.mjd);
  if (mjd <= s[0].mjd) return s[0];
  if (mjd >= s[s.length - 1].mjd) return s[s.length - 1];
  for (let i = 0; i < s.length - 1; i++) {
    if (mjd >= s[i].mjd && mjd <= s[i + 1].mjd) {
      const t = (mjd - s[i].mjd) / Math.max(1e-9, s[i + 1].mjd - s[i].mjd);
      return { mjd, ra: s[i].ra + t * (s[i + 1].ra - s[i].ra), dec: s[i].dec + t * (s[i + 1].dec - s[i].dec), x: 0, y: 0 };
    }
  }
  return s[s.length - 1];
}

function niceTicks(lo: number, hi: number, target = 5): number[] {
  const span = hi - lo;
  if (!(span > 0)) return [lo];
  const raw = span / target;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const f = raw / p;
  const step = (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * p;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.abs(v) < step * 1e-6 ? 0 : v);
  return out;
}

const tickLabel = (v: number) => (Math.abs(v) >= 10 ? v.toFixed(0) : Math.abs(v) >= 1 ? v.toFixed(1) : v.toFixed(2));

export default function MotionPanel({ inv }: { inv: Investigation }) {
  const astro = inv.astrometry;
  const measured = useMemo(() => astro?.measured ?? [], [astro]);
  const track = useMemo(() => [...(inv.track ?? [])].sort((a, b) => a.mjd - b.mjd), [inv.track]);
  const visitIndex = (id: string) => Math.max(0, inv.visits.findIndex((v) => v.id === id));

  const usable = measured.filter((m) => !m.crowded && !m.saturated);
  const allSaturated = measured.length > 0 && measured.every((m) => m.saturated);

  const geom = useMemo(() => {
    const origin = track[0] ?? (measured[0] ? { ra: measured[0].ra, dec: measured[0].dec, mjd: measured[0].mjd } : null);
    if (!origin) return null;
    const trk = track.map((p) => ({ ...p, off: offsetArcsec(p.ra, p.dec, origin.ra, origin.dec) }));
    const meas = measured.map((m) => {
      const off = offsetArcsec(m.ra, m.dec, origin.ra, origin.dec);
      const hasResid = m.resid_ra_arcsec != null && m.resid_dec_arcsec != null;
      let pred: [number, number] | null = hasResid ? [off[0] - (m.resid_ra_arcsec as number), off[1] - (m.resid_dec_arcsec as number)] : null;
      if (!pred) {
        const p = interpTrack(track, m.mjd);
        if (p) pred = offsetArcsec(p.ra, p.dec, origin.ra, origin.dec);
      }
      return { m, off, pred };
    });
    const xs: number[] = [0];
    const ys: number[] = [0];
    for (const t of trk) {
      xs.push(t.off[0]);
      ys.push(t.off[1]);
    }
    for (const e of meas) {
      const r = e.m.err_arcsec || 0;
      xs.push(e.off[0] - r, e.off[0] + r);
      ys.push(e.off[1] - r, e.off[1] + r);
      if (e.pred) {
        xs.push(e.pred[0]);
        ys.push(e.pred[1]);
      }
    }
    let xMin = Math.min(...xs);
    let xMax = Math.max(...xs);
    let yMin = Math.min(...ys);
    let yMax = Math.max(...ys);
    const padX = Math.max(0.15 * (xMax - xMin), 0.25);
    const padY = Math.max(0.15 * (yMax - yMin), 0.25);
    xMin -= padX;
    xMax += padX;
    yMin -= padY;
    yMax += padY;
    const pw = W - M.l - M.r;
    const ph = H - M.t - M.b;
    const scale = Math.min(pw / (xMax - xMin), ph / (yMax - yMin));
    const cx = (xMin + xMax) / 2;
    const cy = (yMin + yMax) / 2;
    const sx = (dx: number) => M.l + pw / 2 - (dx - cx) * scale; // east (positive dx) to the left
    const sy = (dy: number) => M.t + ph / 2 - (dy - cy) * scale; // north up
    const vx0 = cx - pw / 2 / scale;
    const vx1 = cx + pw / 2 / scale;
    const vy0 = cy - ph / 2 / scale;
    const vy1 = cy + ph / 2 / scale;
    return { origin, trk, meas, scale, sx, sy, xt: niceTicks(vx0, vx1, 5), yt: niceTicks(vy0, vy1, 5), pw, ph };
  }, [track, measured]);

  const predictedMotion = useMemo(() => {
    if (track.length < 2) return null;
    const a = track[0];
    const b = track[track.length - 1];
    const [dx, dy] = offsetArcsec(b.ra, b.dec, a.ra, a.dec);
    return { arcsec: Math.hypot(dx, dy), years: (b.mjd - a.mjd) / 365.25 };
  }, [track]);

  const fit = astro?.fit;
  const cat = astro?.catalog;
  const reg = astro?.registration;

  if (!geom) {
    return (
      <Card title="Motion">
        <EmptyState title="No position data">
          Neither a predicted track nor measured centroids are available. Targets without a catalog proper motion have no
          predicted track, and faint or saturated targets may yield no usable centroids.
        </EmptyState>
      </Card>
    );
  }

  const { sx, sy } = geom;

  return (
    <Card
      title="Motion"
      subtitle="Measured positions against the track predicted from catalog proper motion and parallax"
    >
      {allSaturated && (
        <div className="mb-2">
          <Note tone="amber">
            Saturated in all epochs — motion is shown by the predicted track only. Centroids of saturated stars are
            biased, so they are drawn hollow and excluded from the fit.
          </Note>
        </div>
      )}
      {measured.length === 0 && (
        <div className="mb-2">
          <Note tone="amber">
            No centroid could be measured (low signal, saturation or crowding), so only the predicted track is shown.
          </Note>
        </div>
      )}

      <div className="mx-auto w-full max-w-[440px]">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-auto w-full"
          role="img"
          aria-label="Measured positions and predicted track as arcsecond offsets from the first predicted point; east is left, north is up"
        >
          <rect x={M.l} y={M.t} width={geom.pw} height={geom.ph} fill="#f1f2f0" stroke="#b3b9b6" />
          {geom.xt.map((v) => (
            <g key={`x${v}`}>
              <line x1={sx(v)} x2={sx(v)} y1={M.t} y2={M.t + geom.ph} stroke="#ccd1ce" strokeWidth={0.7} />
              <text x={sx(v)} y={M.t + geom.ph + 13} textAnchor="middle" fontSize={11.5} fill="#4f565b">
                {tickLabel(v)}
              </text>
            </g>
          ))}
          {geom.yt.map((v) => (
            <g key={`y${v}`}>
              <line x1={M.l} x2={M.l + geom.pw} y1={sy(v)} y2={sy(v)} stroke="#ccd1ce" strokeWidth={0.7} />
              <text x={M.l - 5} y={sy(v) + 3} textAnchor="end" fontSize={11.5} fill="#4f565b">
                {tickLabel(v)}
              </text>
            </g>
          ))}
          <text x={M.l + geom.pw / 2} y={H - 6} textAnchor="middle" fontSize={12.5} fill="#4f565b">
            ← East · ΔRA·cosδ (arcsec)
          </text>
          <text
            transform={`translate(11 ${M.t + geom.ph / 2}) rotate(-90)`}
            textAnchor="middle"
            fontSize={12.5}
            fill="#4f565b"
          >
            ΔDec (arcsec) · North ↑
          </text>

          <clipPath id="motion-clip">
            <rect x={M.l} y={M.t} width={geom.pw} height={geom.ph} />
          </clipPath>
          <g clipPath="url(#motion-clip)">
            {geom.trk.length >= 2 && (
              <polyline
                points={geom.trk.map((p) => `${sx(p.off[0])},${sy(p.off[1])}`).join(" ")}
                fill="none"
                stroke="#1f3f8a"
                strokeWidth={1.4}
                strokeDasharray="5 3"
              />
            )}
            {geom.trk.map((p, i) => (
              <circle key={`t${i}`} cx={sx(p.off[0])} cy={sy(p.off[1])} r={2} fill="#1f3f8a" opacity={0.8} />
            ))}
            {/* origin */}
            <g stroke="#121416" strokeWidth={1}>
              <line x1={sx(0) - 5} x2={sx(0) + 5} y1={sy(0)} y2={sy(0)} />
              <line x1={sx(0)} x2={sx(0)} y1={sy(0) - 5} y2={sy(0) + 5} />
            </g>

            {geom.meas.map((e, i) => {
              const color = visitColor(visitIndex(e.m.visit_id));
              const hollow = e.m.crowded || e.m.saturated;
              const cx = sx(e.off[0]);
              const cy = sy(e.off[1]);
              const r = Math.max(2.5, (e.m.err_arcsec || 0) * geom.scale);
              return (
                <g key={`m${i}`}>
                  {e.pred && (
                    <>
                      <line x1={sx(e.pred[0])} y1={sy(e.pred[1])} x2={cx} y2={cy} stroke="#8a5a06" strokeWidth={1.2} />
                      <circle cx={sx(e.pred[0])} cy={sy(e.pred[1])} r={2.5} fill="none" stroke="#1f3f8a" strokeWidth={1.2} />
                    </>
                  )}
                  <circle
                    cx={cx}
                    cy={cy}
                    r={r}
                    fill={hollow ? "none" : color}
                    fillOpacity={hollow ? 0 : 0.18}
                    stroke={color}
                    strokeWidth={1.4}
                    strokeDasharray={hollow ? "3 2" : undefined}
                  />
                  <circle cx={cx} cy={cy} r={2.6} fill={hollow ? "#f1f2f0" : color} stroke={color} strokeWidth={1.4} />
                  <text x={cx + r + 3} y={cy - 3} fontSize={11.5} fill={color}>
                    {i + 1}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden className="inline-block w-5 border-t-2 border-dashed border-accent" />
          predicted track
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-2.5 w-2.5 border-2 border-accent" />
          predicted at epoch
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-2.5 w-2.5 border border-fg bg-panel2" />
          measured ±1σ (numbered by epoch)
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-2.5 w-2.5 border border-dashed border-fg" />
          hollow: crowded or saturated
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden className="inline-block w-5 border-t-2 border-warn" />
          residual (observed − predicted)
        </li>
      </ul>
      {predictedMotion && (
        <p className="mt-2 text-sm text-muted">
          The predicted track covers {num(predictedMotion.arcsec, 2)}″ over {num(predictedMotion.years, 2)} yr
          {predictedMotion.arcsec < 6.15 ? " — less than one SPHEREx pixel (6.15″), so motion is only visible from the centroid fit, not by blinking alone" : ""}.
          Systematic registration uncertainty is about 0.1–0.3″.
        </p>
      )}

      <SectionTitle hint="Residuals are observed − predicted, in arcsec (RA component multiplied by cosδ).">Epochs</SectionTitle>
      {measured.length === 0 ? (
        <p className="text-sm text-muted">No measured epochs.</p>
      ) : (
        <TableWrap>
          <table className="w-full min-w-[480px] border-collapse">
            <thead>
              <tr className="border-b border-line">
                <th className={thCls}>#</th>
                <th className={thCls}>Date</th>
                <th className={thCls}>Visit</th>
                <th className={thCls}>ΔRA* (″)</th>
                <th className={thCls}>ΔDec (″)</th>
                <th className={thCls}>σ (″)</th>
                <th className={thCls}>SNR</th>
                <th className={thCls}>Flags</th>
              </tr>
            </thead>
            <tbody>
              {measured.map((m, i) => (
                <tr key={i} className="border-b border-line last:border-0">
                  <td className={tdCls}>{i + 1}</td>
                  <td className={tdCls}>{mjdToDate(m.mjd)}</td>
                  <td className={tdCls}>
                    <span aria-hidden className="mr-1 inline-block h-2.5 w-2.5" style={{ background: visitColor(visitIndex(m.visit_id)) }} />
                    {m.visit_id}
                    {m.detector === "all" ? "" : ` · D${m.detector}`}
                  </td>
                  <td className={tdCls}>{num(m.resid_ra_arcsec, 2)}</td>
                  <td className={tdCls}>{num(m.resid_dec_arcsec, 2)}</td>
                  <td className={tdCls}>{num(m.err_arcsec, 2)}</td>
                  <td className={tdCls}>{num(m.snr, 1)}</td>
                  <td className={tdCls}>
                    {m.saturated && <span className="mr-1 text-warn">saturated</span>}
                    {m.crowded && <span className="mr-1 text-warn">crowded</span>}
                    {!m.saturated && !m.crowded && <span className="text-good">used</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}

      <SectionTitle hint="Weighted least-squares fit to the usable (unsaturated, uncrowded) epochs.">
        Proper motion: fit vs catalog
      </SectionTitle>
      {!fit ? (
        <p className="text-sm text-muted">
          {usable.length < 2
            ? `No proper-motion fit: it needs at least two usable epochs and only ${usable.length} ${usable.length === 1 ? "is" : "are"} available (others are saturated, crowded or missing).`
            : "No proper-motion fit was produced for this target."}
          {cat && " The catalog values are listed below for comparison."}
        </p>
      ) : null}
      {(fit || cat) && (
        <TableWrap>
          <table className="w-full min-w-[420px] border-collapse">
            <thead>
              <tr className="border-b border-line">
                <th className={thCls}>Source</th>
                <th className={thCls}>µα* (mas/yr)</th>
                <th className={thCls}>µδ (mas/yr)</th>
                <th className={thCls}>
                  χ²<sub>red</sub>
                </th>
                <th className={thCls}>Baseline</th>
                <th className={thCls}>Parallax (mas)</th>
              </tr>
            </thead>
            <tbody>
              {fit && (
                <tr className="border-b border-line">
                  <td className={tdCls}>SPHEREx fit ({fit.n_points} pts)</td>
                  <td className={tdCls}>
                    {num(fit.pm_ra, 1)} ± {num(fit.pm_ra_err, 1)}
                  </td>
                  <td className={tdCls}>
                    {num(fit.pm_dec, 1)} ± {num(fit.pm_dec_err, 1)}
                  </td>
                  <td className={tdCls}>{num(fit.chi2_red, 2)}</td>
                  <td className={tdCls}>{num(fit.baseline_yr, 2)} yr</td>
                  <td className={tdCls}>
                    {fit.parallax_mode === "fitted"
                      ? `${num(fit.parallax, 1)} ± ${num(fit.parallax_err, 1)} (fitted)`
                      : fit.parallax_mode === "fixed_catalog"
                        ? "fixed to catalog"
                        : "not modelled"}
                  </td>
                </tr>
              )}
              {cat && (
                <tr>
                  <td className={tdCls}>Catalog ({cat.source})</td>
                  <td className={tdCls}>{num(cat.pm_ra, 1)}</td>
                  <td className={tdCls}>{num(cat.pm_dec, 1)}</td>
                  <td className={tdCls}>—</td>
                  <td className={tdCls}>—</td>
                  <td className={tdCls}>{num(cat.parallax, 1)}</td>
                </tr>
              )}
            </tbody>
          </table>
        </TableWrap>
      )}
      {fit && astro.consistency_sigma != null && (
        <p className="mt-2 text-sm text-muted">
          Difference from the catalog proper motion:{" "}
          <strong className={astro.consistency_sigma < 3 ? "text-good" : "text-warn"}>
            {num(astro.consistency_sigma, 1)}σ
          </strong>{" "}
          — {astro.consistency_sigma < 3 ? "consistent with the catalog (threshold 3σ)." : "larger than the 3σ consistency threshold; check crowding, registration and saturation before reading anything into it."}
        </p>
      )}
      {fit && fit.baseline_yr < 1 && (
        <p className="mt-1 text-sm text-muted">
          The baseline is under one year, so parallax and proper motion cannot be separated and parallax is not fitted.
        </p>
      )}

      <SectionTitle hint="How well the SPHEREx pointing agrees with Gaia stars in the same frames (reported only; frames are not re-registered).">
        Registration check
      </SectionTitle>
      {reg ? (
        <p className="text-sm text-fg">
          {reg.n_stars} reference stars ({reg.reference === "gaia_dr3" ? "Gaia DR3" : reg.reference}): median offset{" "}
          <span className="tabular-nums">{num(reg.median_offset_arcsec, 2)}″</span>, rms{" "}
          <span className="tabular-nums">{num(reg.rms_arcsec, 2)}″</span>.
        </p>
      ) : (
        <p className="text-sm text-muted">Not available: too few unsaturated Gaia stars in the field.</p>
      )}
    </Card>
  );
}
