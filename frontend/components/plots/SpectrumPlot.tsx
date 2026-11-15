"use client";

import { useMemo, useState } from "react";
import type { Investigation } from "@/lib/types";
import { Card, EmptyState, Note, Toggle, num, sigfig } from "@/components/panels/shared";
import LazyPlot from "./LazyPlot";
import {
  FALLBACK_DET_RANGES,
  PALETTE,
  axisBase,
  baseLayout,
  plotConfig,
  visitColor,
} from "./plotTheme";

interface ClickPoint {
  x?: number | string;
  customdata?: { obs_ids: string[]; n: number; visit: string };
}
interface ClickEvent {
  points?: ClickPoint[];
}

/** Detector wavelength extents derived from the spectrum channel grid (fallback: nominal ranges). */
function detectorExtents(inv: Investigation): { d: number; lo: number; hi: number }[] {
  const ch = inv.spectrum?.channels_um ?? [];
  const cd = inv.spectrum?.channel_detector ?? [];
  const by = new Map<number, number[]>();
  ch.forEach((w, i) => {
    const d = cd[i];
    if (d && Number.isFinite(w)) by.set(d, [...(by.get(d) ?? []), w]);
  });
  const dets = [...by.keys()].sort((a, b) => a - b);
  if (dets.length < 2) {
    return Object.entries(FALLBACK_DET_RANGES).map(([d, [lo, hi]]) => ({ d: Number(d), lo, hi }));
  }
  const mm = dets.map((d) => {
    const a = by.get(d)!;
    return { d, min: Math.min(...a), max: Math.max(...a), n: a.length };
  });
  return mm.map((m, i) => {
    const half = m.n > 1 ? (m.max - m.min) / (2 * (m.n - 1)) : 0.02;
    const lo = i === 0 ? m.min - half : (mm[i - 1].max + m.min) / 2;
    const hi = i === mm.length - 1 ? m.max + half : (m.max + mm[i + 1].min) / 2;
    return { d: m.d, lo, hi };
  });
}

type Quantity = "fnu" | "nufnu";

export default function SpectrumPlot({
  inv,
  onSelectChannel,
}: {
  inv: Investigation;
  onSelectChannel?: (obsIds: string[], wavelengthUm: number) => void;
}) {
  const spec = inv.spectrum;
  const visits = useMemo(() => spec?.visits ?? [], [spec]);
  const hasData = visits.some((v) => v.points.some((p) => p.flux_ujy !== null && Number.isFinite(p.flux_ujy)));

  const nonPositiveShare = useMemo(() => {
    let n = 0;
    let pos = 0;
    for (const v of visits) {
      for (const p of v.points) {
        if (p.flux_ujy === null) continue;
        n += 1;
        if (p.flux_ujy > 0) pos += 1;
      }
    }
    return n === 0 ? 1 : pos / n;
  }, [visits]);

  const [yScale, setYScale] = useState<"log" | "linear">(() => (nonPositiveShare >= 0.9 ? "log" : "linear"));
  const [quantity, setQuantity] = useState<Quantity>("fnu");
  const [showBands, setShowBands] = useState(true);
  const [selected, setSelected] = useState<{ wl: number; n: number; visit: string; obs: string[] } | null>(null);

  const visitLabel = (id: string) => inv.visits.find((v) => v.id === id)?.date_label ?? id;
  const extents = useMemo(() => detectorExtents(inv), [inv]);

  const { data, layout, droppedNonPositive } = useMemo(() => {
    let dropped = 0;
    const conv = (f: number | null, wl: number): number | null => {
      if (f === null || !Number.isFinite(f)) return null;
      return quantity === "fnu" ? f : (2.998 * f) / wl; // νFν in 1e-18 W m^-2
    };
    const traces: Record<string, unknown>[] = visits.map((v, vi) => {
      const pts = [...v.points].sort((a, b) => a.wavelength_um - b.wavelength_um);
      const color = visitColor(vi);
      const y = pts.map((p) => {
        const val = conv(p.flux_ujy, p.wavelength_um);
        if (yScale === "log" && val !== null && val <= 0) dropped++;
        return val;
      });
      const err = pts.map((p) =>
        p.saturated || p.flux_err_ujy === null || p.flux_ujy === null ? 0 : (conv(p.flux_err_ujy, p.wavelength_um) ?? 0),
      );
      return {
        type: "scatter",
        mode: "lines+markers+text",
        name: `${v.visit_id} · ${visitLabel(v.visit_id)}`,
        x: pts.map((p) => p.wavelength_um),
        y,
        connectgaps: false,
        line: { color, width: 1.2 },
        marker: {
          color,
          size: 7,
          symbol: pts.map((p) => (p.saturated ? "circle-open" : "circle")),
          line: { color, width: 1.8 },
        },
        text: pts.map((p) => (p.saturated && p.flux_ujy !== null ? "≥" : "")),
        textposition: "top center",
        textfont: { color, size: 12 },
        error_y: { type: "data", array: err, visible: true, color, thickness: 1, width: 2 },
        hoverinfo: "text",
        hovertext: pts.map((p) =>
          p.flux_ujy === null
            ? `${v.visit_id} · λ ${num(p.wavelength_um, 3)} µm<br>no data (gap)`
            : `${v.visit_id} · ${visitLabel(v.visit_id)}<br>λ ${num(p.wavelength_um, 3)} µm<br>${
                p.saturated ? "≥ " : ""
              }${sigfig(p.flux_ujy)} ± ${sigfig(p.flux_err_ujy)} µJy${
                p.saturated ? "<br>saturated: lower limit" : ""
              }<br>${p.n} exposure${p.n === 1 ? "" : "s"} — click to select`,
        ),
        customdata: pts.map((p) => ({ obs_ids: p.obs_ids, n: p.n, visit: v.visit_id })),
      };
    });
    // Legend key for hollow markers.
    traces.push({
      type: "scatter",
      mode: "markers",
      name: "○ hollow = saturated (lower limit ≥)",
      x: [null],
      y: [null],
      marker: { color: PALETTE.muted, size: 7, symbol: "circle-open", line: { color: PALETTE.muted, width: 1.8 } },
      hoverinfo: "skip",
    });

    const shapes: Record<string, unknown>[] = extents.map((e, i) => ({
      type: "rect",
      xref: "x",
      yref: "paper",
      x0: e.lo,
      x1: e.hi,
      y0: 0,
      y1: 1,
      fillcolor: i % 2 === 0 ? "rgba(116, 199, 218,0.05)" : "rgba(255,255,255,0.0)",
      line: { color: PALETTE.border, width: 1, dash: "dot" },
      layer: "below",
    }));
    const annotations: Record<string, unknown>[] = extents.map((e) => ({
      x: (e.lo + e.hi) / 2,
      y: 1,
      xref: "x",
      yref: "paper",
      text: `D${e.d}`,
      showarrow: false,
      yanchor: "bottom",
      font: { size: 10, color: PALETTE.muted },
    }));
    if (showBands) {
      for (const f of spec?.features ?? []) {
        shapes.push({
          type: "rect",
          xref: "x",
          yref: "paper",
          x0: f.wavelength_um - 0.04,
          x1: f.wavelength_um + 0.04,
          y0: 0,
          y1: 1,
          fillcolor: "rgba(242,184,75,0.13)",
          line: { width: 0 },
          layer: "below",
        });
        annotations.push({
          x: f.wavelength_um,
          y: 0.02,
          xref: "x",
          yref: "paper",
          text: f.species,
          textangle: -90,
          showarrow: false,
          yanchor: "bottom",
          xanchor: "center",
          font: { size: 9, color: "#c9a04a" },
          hovertext: f.note,
        });
      }
    }
    const allLo = Math.min(...extents.map((e) => e.lo));
    const allHi = Math.max(...extents.map((e) => e.hi));
    const layout = baseLayout({
      height: 380,
      margin: { l: 56, r: 10, t: 24, b: 80 },
      xaxis: axisBase("Wavelength (µm)", { range: [allLo, allHi] }),
      yaxis: axisBase(quantity === "fnu" ? "Flux density Fν (µJy)" : "νFν (10⁻¹⁸ W m⁻²)", { type: yScale }),
      shapes,
      annotations,
    });
    return { data: traces, layout, droppedNonPositive: dropped };
    // visitLabel depends only on inv.visits
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visits, extents, quantity, yScale, showBands, spec, inv.visits]);

  const handleClick = (ev: ClickEvent) => {
    const p = ev.points?.[0];
    const cd = p?.customdata;
    if (!p || !cd) return;
    const wl = Number(p.x);
    setSelected({ wl, n: cd.n, visit: cd.visit, obs: cd.obs_ids });
    onSelectChannel?.(cd.obs_ids, wl);
  };

  return (
    <Card
      title="Spectrum"
      subtitle="Flux density vs wavelength, one trace per visit"
      right={
        <>
          <Toggle
            label="Y axis scale"
            value={yScale}
            onChange={(v) => setYScale(v as "log" | "linear")}
            options={[
              { value: "log", label: "Log y" },
              { value: "linear", label: "Linear y" },
            ]}
          />
          <Toggle
            label="Plotted quantity"
            value={quantity}
            onChange={(v) => setQuantity(v as Quantity)}
            options={[
              { value: "fnu", label: "Fν" },
              { value: "nufnu", label: "νFν" },
            ]}
          />
        </>
      }
    >
      {!hasData ? (
        <EmptyState title="No spectrum data yet">
          Spectra need unsaturated or lower-limit measurements across several detectors. If the investigation is still
          running, this panel fills in as the measurement stage finishes.
        </EmptyState>
      ) : (
        <>
          <div role="img" aria-label="Spectrum: flux density versus wavelength for each visit" className="w-full">
            <LazyPlot
              data={data}
              layout={layout}
              config={plotConfig}
              useResizeHandler
              style={{ width: "100%", height: 380 }}
              onClick={handleClick}
            />
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[#8a97b4]">
            <label className="inline-flex cursor-pointer items-center gap-1.5">
              <input
                type="checkbox"
                checked={showBands}
                onChange={(e) => setShowBands(e.target.checked)}
                className="h-3.5 w-3.5 accent-[#f2b84b]"
              />
              <span>
                Show molecular <span className="text-[#f2b84b]">reference bands</span> — not detections
              </span>
            </label>
          </div>

          <ul className="mt-2 space-y-1 text-xs leading-relaxed text-[#8a97b4]">
            <li>
              Hollow markers marked “≥” are <strong className="text-[#e6ebf5]">saturated: lower limits</strong>, shown
              without error bars. Broken lines are gaps where no usable data exist.
            </li>
            <li>
              Amber bands are literature reference positions for common molecules. SPHEREx spectra have low resolution
              (R ≈ 40–130), so a band overlapping the data does not mean the molecule is detected.
            </li>
            <li>
              {spec?.wavelength_source === "wcs_wave"
                ? "λ from SPHEREx WCS-WAVE table at the target pixel."
                : "λ approximated from detector band centre (the per-pixel wavelength table was not used)."}
              {quantity === "nufnu" && " νFν computed as 2.998 × Fν[µJy] / λ[µm] (units of 10⁻¹⁸ W m⁻²)."}
              {yScale === "log" && droppedNonPositive > 0 && ` ${droppedNonPositive} non-positive point(s) cannot be drawn on a log axis; switch to linear to see them.`}
            </li>
          </ul>

          {selected && (
            <div className="mt-2">
              <Note tone="cyan">
                Selected channel: λ = {num(selected.wl, 3)} µm, visit {selected.visit}, {selected.n} exposure
                {selected.n === 1 ? "" : "s"}
                {selected.obs.length > 0 && (
                  <>
                    {" "}
                    (<span className="break-all font-mono">{selected.obs.slice(0, 3).join(", ")}</span>
                    {selected.obs.length > 3 ? ` +${selected.obs.length - 3} more` : ""})
                  </>
                )}
                .
              </Note>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
