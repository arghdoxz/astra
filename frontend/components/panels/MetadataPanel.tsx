"use client";

import { useMemo, useState } from "react";
import type { Detector, Investigation } from "@/lib/types";
import { DETECTOR_RANGES } from "@/lib/format";
import { Card, EmptyState, SectionTitle, TableWrap, inputCls, mjdToDate, num, sigfig, tdCls, thCls } from "./shared";

const CONTAM = /PERSIST|GHOST|HALO|BLOOM|STREAK|CROSSTALK|SNOWBALL/i;

function median(a: number[]): number | null {
  const v = a.filter((x) => Number.isFinite(x)).sort((x, y) => x - y);
  if (v.length === 0) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

export default function MetadataPanel({
  inv,
  selectedVisit,
  detector,
}: {
  inv: Investigation;
  selectedVisit?: string | null;
  detector?: Detector | null;
}) {
  // Local choice that follows the parent's selection whenever the parent changes it.
  const [localVisit, setLocalVisit] = useState<string | null>(null);
  const [prevVisit, setPrevVisit] = useState(selectedVisit);
  if (prevVisit !== selectedVisit) {
    setPrevVisit(selectedVisit);
    setLocalVisit(null);
  }
  const [localDet, setLocalDet] = useState<Detector | null>(null);
  const [prevDet, setPrevDet] = useState(detector);
  if (prevDet !== detector) {
    setPrevDet(detector);
    setLocalDet(null);
  }
  const [showAll, setShowAll] = useState(false);

  const visitId = localVisit ?? selectedVisit ?? inv.visits[0]?.id ?? null;
  const det: Detector = localDet ?? detector ?? "all";
  const visit = inv.visits.find((v) => v.id === visitId) ?? null;

  const exps = useMemo(
    () =>
      inv.exposures
        .filter((e) => e.visit_id === visitId && (det === "all" || e.detector === det))
        .sort((a, b) => a.mjd - b.mjd || a.detector - b.detector),
    [inv.exposures, visitId, det],
  );

  const stats = useMemo(() => {
    const versions = [...new Set(exps.map((e) => e.pipeline_version).filter((x): x is string => !!x))];
    const flags = new Map<string, number>();
    for (const e of exps) for (const [k, v] of Object.entries(e.flag_counts ?? {})) flags.set(k, (flags.get(k) ?? 0) + v);
    const topFlags = [...flags.entries()].filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    return {
      versions,
      psf: median(exps.map((e) => e.psf_fwhm_arcsec).filter((x): x is number => x != null)),
      variance: median(exps.map((e) => e.variance_median).filter((x): x is number => x != null)),
      ok: exps.filter((e) => e.status === "ok").length,
      topFlags,
    };
  }, [exps]);

  const coverage = useMemo(() => {
    const m = new Map<string, number>();
    for (const e of inv.exposures) m.set(`${e.visit_id}|${e.detector}`, (m.get(`${e.visit_id}|${e.detector}`) ?? 0) + 1);
    return m;
  }, [inv.exposures]);

  if (inv.visits.length === 0) {
    return (
      <Card title="Observation details">
        <EmptyState title="No visits found">SPHEREx has not (yet) observed this position in the searched releases.</EmptyState>
      </Card>
    );
  }

  const range = det === "all" ? null : DETECTOR_RANGES[det];
  const rowsShown = showAll ? exps : exps.slice(0, 8);

  return (
    <Card
      title="Observation details"
      subtitle="Metadata for one visit and detector"
      right={
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1 text-sm text-muted">
            Visit
            <select
              className={`${inputCls} w-auto`}
              value={visitId ?? ""}
              onChange={(e) => setLocalVisit(e.target.value)}
              aria-label="Visit"
            >
              {inv.visits.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.id} · {v.date_label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1 text-sm text-muted">
            Detector
            <select
              className={`${inputCls} w-auto`}
              value={String(det)}
              onChange={(e) => setLocalDet(e.target.value === "all" ? "all" : Number(e.target.value))}
              aria-label="Detector"
            >
              <option value="all">All</option>
              {[1, 2, 3, 4, 5, 6].map((d) => (
                <option key={d} value={d}>
                  D{d}
                </option>
              ))}
            </select>
          </label>
        </div>
      }
    >
      {visit && (
        <dl className="grid grid-cols-1 gap-x-4 gap-y-1.5 text-sm sm:grid-cols-2">
          <Item k="Dates (UTC)" v={`${mjdToDate(visit.mjd_start)} → ${mjdToDate(visit.mjd_end)}`} />
          <Item k="MJD" v={`${num(visit.mjd_start, 3)} – ${num(visit.mjd_end, 3)} (mean ${num(visit.mjd_mean, 3)})`} />
          <Item k="Collection" v={visit.collection} />
          <Item k="Pipeline version" v={stats.versions.length ? stats.versions.join(", ") : "not reported"} />
          <Item
            k="Detector λ range"
            v={range ? `D${det}: ${range[0].toFixed(2)}–${range[1].toFixed(2)} µm` : "all six detectors, 0.75–5.0 µm"}
          />
          <Item k="Exposures" v={`${exps.length} selected (${stats.ok} ok) of ${visit.n_exposures} in this visit`} />
          <Item k="PSF FWHM (median)" v={stats.psf === null ? "—" : `${num(stats.psf, 2)}″`} />
          <Item k="Variance (median)" v={stats.variance === null ? "—" : `${sigfig(stats.variance, 3)} MJy²/sr²`} />
        </dl>
      )}

      <SectionTitle hint="Wavelength is the value at the target pixel (the linear variable filter shifts it across the array).">
        Exposures
      </SectionTitle>
      {exps.length === 0 ? (
        <p className="text-sm text-muted">No exposures for this visit and detector.</p>
      ) : (
        <>
          <TableWrap>
            <table className="w-full min-w-[460px] border-collapse">
              <thead>
                <tr className="border-b border-line">
                  <th className={thCls}>Exposure</th>
                  <th className={thCls}>D</th>
                  <th className={thCls}>Date</th>
                  <th className={thCls}>λ (µm)</th>
                  <th className={thCls}>Δλ (µm)</th>
                  <th className={thCls}>PSF (″)</th>
                  <th className={thCls}>Exp (s)</th>
                </tr>
              </thead>
              <tbody>
                {rowsShown.map((e) => (
                  <tr key={e.obs_id} className="border-b border-line last:border-0">
                    <td className={`${tdCls} max-w-[9rem] truncate mono`} title={e.obs_id}>
                      {e.obs_id}
                    </td>
                    <td className={tdCls}>{e.detector}</td>
                    <td className={tdCls}>{e.date_obs?.slice(0, 10) ?? mjdToDate(e.mjd)}</td>
                    <td className={tdCls}>{num(e.wavelength_um, 3)}</td>
                    <td className={tdCls}>{num(e.bandwidth_um, 3)}</td>
                    <td className={tdCls}>{num(e.psf_fwhm_arcsec, 2)}</td>
                    <td className={tdCls}>{num(e.exptime_s, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          {exps.length > 8 && (
            <button
              type="button"
              onClick={() => setShowAll((s) => !s)}
              className="mt-1 text-sm text-accent underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-pencil"
            >
              {showAll ? "Show fewer" : `Show all ${exps.length}`}
            </button>
          )}
        </>
      )}

      <SectionTitle hint="Pixels flagged inside the cutout. Contamination flags (amber) can fake or hide real changes.">
        Quality flags
      </SectionTitle>
      {stats.topFlags.length === 0 ? (
        <p className="text-sm text-muted">No flagged pixels recorded for this selection.</p>
      ) : (
        <ul className="flex flex-wrap gap-1.5">
          {stats.topFlags.slice(0, 8).map(([k, v]) => (
            <li
              key={k}
              className={`chip ${CONTAM.test(k) ? "chip-amber" : ""}`}
              title={CONTAM.test(k) ? "Contamination flag" : undefined}
            >
              {k} <span className="tabular-nums text-fg">{v}</span>
            </li>
          ))}
        </ul>
      )}

      <SectionTitle hint="Number of exposures found per visit and detector.">Coverage</SectionTitle>
      <TableWrap>
        <table className="w-full min-w-[300px] border-collapse text-center">
          <thead>
            <tr className="border-b border-line">
              <th className={thCls}>Visit</th>
              {[1, 2, 3, 4, 5, 6].map((d) => (
                <th key={d} className={`${thCls} text-center`}>
                  D{d}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {inv.visits.map((v) => (
              <tr key={v.id} className="border-b border-line last:border-0">
                <td className={`${tdCls} text-left`}>
                  {v.id} <span className="text-muted">{v.date_label}</span>
                </td>
                {[1, 2, 3, 4, 5, 6].map((d) => {
                  const n = coverage.get(`${v.id}|${d}`) ?? 0;
                  const sel = v.id === visitId && (det === "all" || det === d);
                  return (
                    <td
                      key={d}
                      className={`${tdCls} text-center ${n ? "text-fg" : "text-muted"} ${sel ? "bg-panel2 font-semibold" : ""}`}
                    >
                      {n || "·"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    </Card>
  );
}

function Item({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-2 border-b border-line pb-1">
      <dt className="text-muted">{k}</dt>
      <dd className="text-right tabular-nums text-fg">{v}</dd>
    </div>
  );
}
