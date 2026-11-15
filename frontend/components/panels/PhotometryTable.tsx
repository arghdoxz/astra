"use client";

import { useMemo, useState } from "react";
import type { Investigation, PhotPoint } from "@/lib/types";
import { isLive, reportUrl } from "@/lib/api";
import { Card, EmptyState, TableWrap, btn, inputCls, mjdToDate, num, sigfig, tdCls, thCls } from "./shared";

type SortKey = "mjd" | "detector" | "wavelength_um" | "flux_ujy" | "snr" | "ab_mag" | "saturated" | "flagged_frac" | "contam" | "outlier";

const COLS: { key: SortKey; label: string; title?: string }[] = [
  { key: "mjd", label: "Date" },
  { key: "detector", label: "D" },
  { key: "wavelength_um", label: "λ (µm)" },
  { key: "flux_ujy", label: "Flux ± σ (µJy)" },
  { key: "snr", label: "SNR" },
  { key: "ab_mag", label: "AB mag" },
  { key: "saturated", label: "Sat.", title: "Saturated: flux is a lower limit" },
  { key: "flagged_frac", label: "Flagged", title: "Fraction of aperture pixels hard-masked" },
  { key: "contam", label: "Contamination" },
  { key: "outlier", label: "Outlier" },
];

function sortValue(p: PhotPoint, k: SortKey): number {
  switch (k) {
    case "contam":
      return p.contamination_bits.length;
    case "saturated":
      return p.saturated ? 1 : 0;
    case "outlier":
      return p.outlier ? 1 : 0;
    default: {
      const v = p[k as keyof PhotPoint] as number | null;
      return v === null || v === undefined ? Number.NEGATIVE_INFINITY : v;
    }
  }
}

function csvCell(v: unknown): string {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export default function PhotometryTable({ inv }: { inv: Investigation }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "mjd", dir: 1 });
  const [det, setDet] = useState<string>("all");
  const [limit, setLimit] = useState(100);
  const live = isLive(inv);

  const dets = useMemo(() => [...new Set(inv.photometry.map((p) => p.detector))].sort((a, b) => a - b), [inv.photometry]);
  const rows = useMemo(() => {
    const r = inv.photometry.filter((p) => det === "all" || p.detector === Number(det));
    return [...r].sort((a, b) => {
      const d = sortValue(a, sort.key) - sortValue(b, sort.key);
      return (Number.isNaN(d) || d === 0 ? a.mjd - b.mjd || a.wavelength_um - b.wavelength_um : d) * sort.dir;
    });
  }, [inv.photometry, det, sort]);

  const downloadClientCsv = () => {
    const head = ["obs_id", "visit_id", "detector", "mjd", "wavelength_um", "bandwidth_um", "flux_ujy", "flux_err_ujy", "ab_mag", "snr", "saturated", "flagged_frac", "contamination_bits", "outlier"];
    const lines = [head.join(",")].concat(
      rows.map((p) =>
        [p.obs_id, p.visit_id, p.detector, p.mjd, p.wavelength_um, p.bandwidth_um, p.flux_ujy, p.flux_err_ujy, p.ab_mag, p.snr, p.saturated, p.flagged_frac, p.contamination_bits.join("|"), p.outlier]
          .map(csvCell)
          .join(","),
      ),
    );
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `astra_${inv.id}_photometry.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const onSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: key === "mjd" || key === "detector" ? 1 : -1 }));

  return (
    <Card
      title="Photometry"
      subtitle={`${rows.length} measurement${rows.length === 1 ? "" : "s"}; saturated values are lower limits (≥)`}
      right={
        <>
          <label className="flex items-center gap-1 text-xs text-[#8a97b4]">
            Detector
            <select className={`${inputCls} w-auto`} value={det} onChange={(e) => { setDet(e.target.value); setLimit(100); }} aria-label="Filter by detector">
              <option value="all">All</option>
              {dets.map((d) => (
                <option key={d} value={d}>
                  D{d}
                </option>
              ))}
            </select>
          </label>
          {live ? (
            <a className={btn} href={reportUrl(inv.id, "csv")} download>
              Download CSV
            </a>
          ) : (
            <button type="button" className={btn} onClick={downloadClientCsv} disabled={rows.length === 0} title="Generated in your browser from the data shown">
              Download CSV
            </button>
          )}
        </>
      }
    >
      {inv.photometry.length === 0 ? (
        <EmptyState title="No photometry yet">Measurements appear here after the measurement stage completes.</EmptyState>
      ) : (
        <>
          <TableWrap>
            <table className="w-full min-w-[720px] border-collapse">
              <thead>
                <tr className="border-b border-[#1d2742]">
                  {COLS.map((c) => (
                    <th
                      key={c.key}
                      className={thCls}
                      aria-sort={sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
                      title={c.title}
                    >
                      <button
                        type="button"
                        onClick={() => onSort(c.key)}
                        className="inline-flex items-center gap-1 uppercase tracking-wide hover:text-[#74c7da] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#74c7da]"
                      >
                        {c.label}
                        <span aria-hidden className="text-[9px]">
                          {sort.key === c.key ? (sort.dir === 1 ? "▲" : "▼") : "↕"}
                        </span>
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, limit).map((p) => (
                  <tr key={`${p.obs_id}-${p.detector}-${p.wavelength_um}`} className={`border-b border-[#1d2742]/60 last:border-0 ${p.outlier ? "bg-[#f26b6b]/5" : ""}`}>
                    <td className={tdCls}>{mjdToDate(p.mjd)}</td>
                    <td className={tdCls}>{p.detector}</td>
                    <td className={tdCls}>{num(p.wavelength_um, 3)}</td>
                    <td className={tdCls}>
                      {p.flux_ujy === null ? "—" : `${p.saturated ? "≥ " : ""}${sigfig(p.flux_ujy)} ± ${sigfig(p.flux_err_ujy)}`}
                    </td>
                    <td className={tdCls}>{num(p.snr, 1)}</td>
                    <td className={tdCls}>{p.saturated ? (p.ab_mag === null ? "—" : `≤ ${num(p.ab_mag, 2)}`) : num(p.ab_mag, 2)}</td>
                    <td className={tdCls}>{p.saturated ? <span className="text-[#f2b84b]">yes</span> : "no"}</td>
                    <td className={tdCls}>{(p.flagged_frac * 100).toFixed(0)}%</td>
                    <td className={`${tdCls} ${p.contamination_bits.length ? "text-[#f2b84b]" : "text-[#8a97b4]"}`}>
                      {p.contamination_bits.length ? p.contamination_bits.join(", ") : "none"}
                    </td>
                    <td className={tdCls}>{p.outlier ? <span className="text-[#f26b6b]">× yes</span> : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          {rows.length > limit && (
            <button type="button" className={`${btn} mt-2`} onClick={() => setLimit((l) => l + 200)}>
              Show more ({rows.length - limit} remaining)
            </button>
          )}
        </>
      )}
    </Card>
  );
}
