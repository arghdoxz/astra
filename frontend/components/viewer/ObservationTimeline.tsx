"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Investigation } from "@/lib/types";
import { mjdToISODate } from "@/lib/format";

const ROW_H = 16;
const TOP = 26;
const LEFT = 34;
const RIGHT = 12;
const AXIS_H = 22;

const STATUS_COLOR: Record<string, string> = {
  ok: "#5ad1e6",
  failed: "#f26b6b",
  skipped: "#5f6b88",
};

export default function ObservationTimeline({
  inv,
  selectedVisit,
  onSelectVisit,
  currentMjd,
}: {
  inv: Investigation;
  selectedVisit?: string | null;
  onSelectVisit?: (id: string) => void;
  currentMjd?: number | null;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((e) => setWidth(Math.round(e[0].contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const { lo, hi } = useMemo(() => {
    const vals: number[] = [];
    inv.exposures.forEach((e) => vals.push(e.mjd));
    inv.visits.forEach((v) => vals.push(v.mjd_start, v.mjd_end));
    if (!vals.length) return { lo: 0, hi: 1 };
    let lo = Math.min(...vals);
    let hi = Math.max(...vals);
    const pad = Math.max(2, (hi - lo) * 0.03);
    lo -= pad;
    hi += pad;
    return { lo, hi };
  }, [inv.exposures, inv.visits]);

  const detectors = [1, 2, 3, 4, 5, 6];
  const height = TOP + detectors.length * ROW_H + AXIS_H;
  const plotW = Math.max(10, width - LEFT - RIGHT);
  const x = (mjd: number) => LEFT + ((mjd - lo) / (hi - lo || 1)) * plotW;

  const ticks = useMemo(() => {
    const out: number[] = [];
    const n = Math.max(2, Math.min(8, Math.floor(plotW / 110)));
    for (let i = 0; i <= n; i++) out.push(lo + ((hi - lo) * i) / n);
    return out;
  }, [lo, hi, plotW]);

  if (!inv.exposures.length && !inv.visits.length) {
    return (
      <div className="card card-pad text-sm text-muted">
        <span className="eyebrow block mb-1">Observation timeline</span>
        Exposures will appear here once SPHEREx coverage has been found.
      </div>
    );
  }

  const nOk = inv.exposures.filter((e) => e.status === "ok").length;

  return (
    <section className="card card-pad" aria-label="Observation timeline">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="h-sec">Observation timeline</h2>
        <div className="flex flex-wrap gap-3 text-xs text-muted">
          <span>
            {inv.exposures.length} exposures ({nOk} ok) in {inv.visits.length} visit{inv.visits.length === 1 ? "" : "s"}
          </span>
          <Legend color={STATUS_COLOR.ok} label="ok" />
          <Legend color={STATUS_COLOR.failed} label="failed" />
          <Legend color={STATUS_COLOR.skipped} label="skipped" />
        </div>
      </div>
      <div ref={wrapRef} className="w-full">
        {width > 0 && (
          <svg width={width} height={height} role="img" aria-label="Timeline of SPHEREx exposures by date and detector" className="block">
            {/* rows */}
            {detectors.map((d, i) => (
              <g key={d}>
                <line x1={LEFT} x2={width - RIGHT} y1={TOP + i * ROW_H + ROW_H / 2} y2={TOP + i * ROW_H + ROW_H / 2} stroke="#1d2742" strokeWidth={1} />
                <text x={LEFT - 6} y={TOP + i * ROW_H + ROW_H / 2 + 4} textAnchor="end" fontSize={10} fill="#8a97b4" className="mono">
                  D{d}
                </text>
              </g>
            ))}
            {/* visit bands */}
            {inv.visits.map((v) => {
              const x0 = x(v.mjd_start);
              const w = Math.max(8, x(v.mjd_end) - x0);
              const sel = selectedVisit === v.id;
              return (
                <g
                  key={v.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`Select visit ${v.id}, ${v.date_label}, ${v.n_exposures} exposures`}
                  aria-pressed={sel}
                  className="cursor-pointer"
                  onClick={() => onSelectVisit?.(v.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelectVisit?.(v.id);
                    }
                  }}
                >
                  <rect x={x0 - 3} y={TOP - 4} width={w + 6} height={detectors.length * ROW_H + 8} rx={4} fill={sel ? "rgba(90,209,230,0.16)" : "rgba(90,209,230,0.07)"} stroke={sel ? "#5ad1e6" : "rgba(90,209,230,0.25)"} strokeWidth={1} />
                  <text x={x0 + w / 2} y={TOP - 9} textAnchor="middle" fontSize={10} fill={sel ? "#5ad1e6" : "#8a97b4"}>
                    {v.id} · {v.date_label}
                  </text>
                  <title>{`${v.id}: ${v.date_label}, ${v.n_exposures} exposures (${v.collection})`}</title>
                </g>
              );
            })}
            {/* exposures */}
            {inv.exposures.map((e) => {
              const row = e.detector - 1;
              if (row < 0 || row > 5) return null;
              return (
                <rect
                  key={`${e.obs_id}:${e.detector}`}
                  x={x(e.mjd) - 1.5}
                  y={TOP + row * ROW_H + 3}
                  width={3}
                  height={ROW_H - 6}
                  fill={STATUS_COLOR[e.status] ?? STATUS_COLOR.skipped}
                  pointerEvents="none"
                >
                  <title>{`${e.obs_id} · D${e.detector} · ${mjdToISODate(e.mjd)} · ${e.status}`}</title>
                </rect>
              );
            })}
            {/* current marker */}
            {currentMjd != null && currentMjd >= lo && currentMjd <= hi && (
              <g pointerEvents="none">
                <line x1={x(currentMjd)} x2={x(currentMjd)} y1={TOP - 6} y2={TOP + detectors.length * ROW_H + 4} stroke="#f2b84b" strokeWidth={1.5} />
                <path d={`M${x(currentMjd) - 4} ${TOP + detectors.length * ROW_H + 10} L${x(currentMjd) + 4} ${TOP + detectors.length * ROW_H + 10} L${x(currentMjd)} ${TOP + detectors.length * ROW_H + 4} Z`} fill="#f2b84b" />
              </g>
            )}
            {/* axis */}
            <g>
              {ticks.map((t, i) => (
                <g key={i}>
                  <line x1={x(t)} x2={x(t)} y1={TOP + detectors.length * ROW_H + 4} y2={TOP + detectors.length * ROW_H + 8} stroke="#5f6b88" />
                  <text x={x(t)} y={height - 3} textAnchor={i === 0 ? "start" : i === ticks.length - 1 ? "end" : "middle"} fontSize={10} fill="#8a97b4" className="mono">
                    {mjdToISODate(t).slice(0, 7)}
                  </text>
                </g>
              ))}
            </g>
          </svg>
        )}
      </div>
    </section>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span aria-hidden className="inline-block h-2.5 w-1 rounded-sm" style={{ background: color }} />
      {label}
    </span>
  );
}
