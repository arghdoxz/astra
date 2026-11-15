"use client";

import { useMemo, useState } from "react";
import type { Investigation } from "@/lib/types";
import { Card, EmptyState, Note, SectionTitle, TableWrap, Toggle, num, sigfig, tdCls, thCls } from "@/components/panels/shared";
import LazyPlot from "./LazyPlot";
import { PALETTE, axisBase, baseLayout, detColor, mjdToIso, plotConfig } from "./plotTheme";

const SYS_FLOOR = 0.02; // 2% of flux, added in quadrature (SCIENCE_REFERENCE §2.5)

export default function LightCurvePlot({ inv }: { inv: Investigation }) {
  const phot = useMemo(() => inv.photometry ?? [], [inv.photometry]);
  const [mode, setMode] = useState<"abs" | "rel">("abs");
  const [off, setOff] = useState<ReadonlySet<number>>(new Set());

  const available = useMemo(
    () =>
      [...new Set(phot.filter((p) => p.flux_ujy !== null).map((p) => p.detector))].sort((a, b) => a - b),
    [phot],
  );
  const hasRel = phot.some((p) => p.rel_flux !== null && p.rel_flux !== undefined);
  const effMode = mode === "rel" && hasRel ? "rel" : "abs";
  const shown = useMemo(() => available.filter((d) => !off.has(d)), [available, off]);

  const toggleDet = (d: number) =>
    setOff((prev) => {
      const next = new Set(prev);
      if (next.has(d)) next.delete(d);
      else next.add(d);
      return next;
    });

  const { data, layout, plotted } = useMemo(() => {
    let plotted = 0;
    const traces: Record<string, unknown>[] = [];
    for (const d of shown) {
      const pts = phot
        .filter((p) => p.detector === d && p.flux_ujy !== null && (effMode === "abs" || (p.rel_flux !== null && p.rel_flux !== undefined)))
        .sort((a, b) => a.mjd - b.mjd);
      if (pts.length === 0) continue;
      const color = detColor(d);
      const y = pts.map((p) => (effMode === "abs" ? p.flux_ujy : (p.rel_flux as number)));
      const err = pts.map((p) => {
        if (p.saturated || p.flux_ujy === null) return 0;
        const e = Math.hypot(p.flux_err_ujy ?? 0, SYS_FLOOR * Math.abs(p.flux_ujy));
        if (effMode === "abs") return e;
        return p.flux_ujy !== 0 ? Math.abs((p.rel_flux as number) * e) / Math.abs(p.flux_ujy) : 0;
      });
      plotted += pts.length;
      traces.push({
        type: "scatter",
        mode: "markers",
        name: `D${d}`,
        x: pts.map((p) => mjdToIso(p.mjd)),
        y,
        marker: {
          color,
          size: 8,
          symbol: pts.map((p) => (p.outlier ? "x" : p.saturated ? "circle-open" : "circle")),
          line: { color, width: 1.8 },
        },
        error_y: { type: "data", array: err, visible: true, color, thickness: 1, width: 2 },
        hoverinfo: "text",
        hovertext: pts.map(
          (p) =>
            `D${d} · ${p.visit_id}<br>${p.obs_id}<br>λ ${num(p.wavelength_um, 3)} µm<br>${p.saturated ? "≥ " : ""}${sigfig(p.flux_ujy)} ± ${sigfig(p.flux_err_ujy)} µJy${
              effMode === "rel" ? `<br>relative flux ${num(p.rel_flux, 3)}` : ""
            }${p.saturated ? "<br>saturated: lower limit" : ""}${p.outlier ? "<br>outlier (excluded from χ²)" : ""}`,
        ),
      });
    }
    traces.push(
      {
        type: "scatter",
        mode: "markers",
        name: "○ hollow = saturated (lower limit ≥)",
        x: [null],
        y: [null],
        marker: { color: PALETTE.muted, size: 8, symbol: "circle-open", line: { color: PALETTE.muted, width: 1.8 } },
        hoverinfo: "skip",
      },
      {
        type: "scatter",
        mode: "markers",
        name: "× outlier (> 5 MAD-σ)",
        x: [null],
        y: [null],
        marker: { color: PALETTE.muted, size: 8, symbol: "x", line: { color: PALETTE.muted, width: 1.8 } },
        hoverinfo: "skip",
      },
    );

    const shapes: Record<string, unknown>[] = [];
    const annotations: Record<string, unknown>[] = [];
    inv.visits.forEach((v, i) => {
      const start = Math.min(v.mjd_start, v.mjd_mean) - 0.5;
      const end = Math.max(v.mjd_end, v.mjd_mean) + 0.5;
      shapes.push({
        type: "rect",
        xref: "x",
        yref: "paper",
        x0: mjdToIso(start),
        x1: mjdToIso(end),
        y0: 0,
        y1: 1,
        fillcolor: i % 2 === 0 ? "rgba(90,209,230,0.07)" : "rgba(242,184,75,0.06)",
        line: { width: 0 },
        layer: "below",
      });
      annotations.push({
        x: mjdToIso((start + end) / 2),
        y: 1,
        xref: "x",
        yref: "paper",
        text: v.id,
        showarrow: false,
        yanchor: "bottom",
        font: { size: 10, color: PALETTE.muted },
      });
    });

    const layout = baseLayout({
      height: 360,
      margin: { l: 58, r: 10, t: 24, b: 80 },
      xaxis: axisBase("Date (UTC)", { type: "date" }),
      yaxis: axisBase(effMode === "abs" ? "Flux density Fν (µJy)" : "Flux relative to reference visit", {
        type: "linear",
      }),
      shapes,
      annotations,
    });
    return { data: traces, layout, plotted };
  }, [phot, shown, effMode, inv.visits]);

  const metrics = inv.lightcurve?.metrics ?? [];

  return (
    <Card
      title="Light curve"
      subtitle="Flux vs date, one colour per detector; shaded bands are visits"
      right={
        <Toggle
          label="Flux scale"
          value={effMode}
          onChange={(v) => setMode(v as "abs" | "rel")}
          options={[
            { value: "abs", label: "Absolute µJy" },
            { value: "rel", label: "Relative" },
          ]}
        />
      }
    >
      {available.length === 0 ? (
        <EmptyState title="No photometry to plot">
          No usable flux measurements are available for this target yet. If the investigation is still running, this
          panel fills in after the measurement stage.
        </EmptyState>
      ) : (
        <>
          <fieldset className="mb-2">
            <legend className="mb-1 text-xs text-[#8a97b4]">Detectors shown</legend>
            <div className="flex flex-wrap gap-1.5">
              {available.map((d) => {
                const on = !off.has(d);
                return (
                  <label
                    key={d}
                    className={`inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-2 py-1 text-xs focus-within:outline focus-within:outline-2 focus-within:outline-[#5ad1e6] ${
                      on ? "border-[#5ad1e6]/40 bg-[#5ad1e6]/10 text-[#e6ebf5]" : "border-[#1d2742] text-[#8a97b4]"
                    }`}
                  >
                    <input type="checkbox" className="sr-only" checked={on} onChange={() => toggleDet(d)} />
                    <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: detColor(d), opacity: on ? 1 : 0.3 }} />
                    D{d}
                  </label>
                );
              })}
            </div>
          </fieldset>

          {mode === "rel" && !hasRel && (
            <div className="mb-2">
              <Note tone="amber">
                Relative flux is unavailable (no reference visit with ≥ 3 unsaturated points), so absolute flux is shown.
              </Note>
            </div>
          )}

          {shown.length === 0 || plotted === 0 ? (
            <EmptyState title="No detectors selected">Tick at least one detector above to draw the light curve.</EmptyState>
          ) : (
            <div role="img" aria-label="Light curve: flux versus date per detector" className="w-full">
              <LazyPlot
                data={data}
                layout={layout}
                config={plotConfig}
                useResizeHandler
                style={{ width: "100%", height: 360 }}
              />
            </div>
          )}

          <ul className="mt-2 space-y-1 text-xs leading-relaxed text-[#8a97b4]">
            <li>
              Error bars include a <strong className="text-[#e6ebf5]">2% systematic floor</strong> added in quadrature
              to the photometric error. Hollow markers are saturated lower limits (no error bar); × marks outliers, which
              are excluded from χ².
            </li>
            <li>
              Each detector samples different wavelengths within a visit, so compare the same detector across visits
              rather than points within one visit.
              {effMode === "rel" && " Relative flux is divided by the median of the same wavelength bin in the reference visit; its error bar is scaled from the absolute error."}
            </li>
          </ul>
        </>
      )}

      <div className="mt-3">
        <Note tone="amber">
          <strong>Period:</strong> {inv.lightcurve?.period_note || "ASTRA does not fit or claim a period from a handful of survey visits."}
        </Note>
      </div>

      <SectionTitle
        hint={
          <>
            Variability is flagged only when χ²<sub>red</sub> &gt; 5 and amplitude &gt; 5σ in at least two detectors moving the
            same way{inv.lightcurve ? ` (detectors changing coherently: ${inv.lightcurve.coherent_detectors}${inv.lightcurve.reference_visit ? `; reference visit ${inv.lightcurve.reference_visit}` : ""})` : ""}.
          </>
        }
      >
        Variability metrics
      </SectionTitle>
      {metrics.length === 0 ? (
        <p className="text-xs text-[#8a97b4]">No variability metrics were computed (too few unsaturated points).</p>
      ) : (
        <TableWrap>
          <table className="w-full min-w-[420px] border-collapse">
            <thead>
              <tr className="border-b border-[#1d2742]">
                <th className={thCls}>Detector</th>
                <th className={thCls}>n</th>
                <th className={thCls}>
                  χ²<sub>red</sub>
                </th>
                <th className={thCls}>Amp (σ)</th>
                <th className={thCls}>Frac. amp</th>
                <th className={thCls}>Significant</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map((m) => (
                <tr key={m.detector} className="border-b border-[#1d2742]/60 last:border-0">
                  <td className={tdCls}>
                    <span aria-hidden className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: detColor(m.detector) }} />D{m.detector}
                  </td>
                  <td className={tdCls}>{m.n}</td>
                  <td className={tdCls}>{num(m.chi2_red, 2)}</td>
                  <td className={tdCls}>{num(m.amp_sigma, 1)}</td>
                  <td className={tdCls}>{m.frac_amp === null ? "—" : `${(m.frac_amp * 100).toFixed(1)}%`}</td>
                  <td className={tdCls}>
                    {m.significant ? <span className="text-[#59d98e]">✓ yes</span> : <span className="text-[#8a97b4]">no</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </Card>
  );
}
