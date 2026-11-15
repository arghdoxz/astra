// Shared plate-archive theme for Plotly charts: ink on paper (no plotly import here).

export const PALETTE = {
  paper: "#f1f2f0",
  ink: "#121416",
  muted: "#4f565b",
  grid: "#d2d6d3",
  axis: "#4f565b",
  border: "#b3b9b6",
  blue: "#1f3f8a",
  pencil: "#b42d1c",
  moss: "#2f6430",
  ochre: "#8a5a06",
  plum: "#7a3a6a",
};

/** One colour per visit; each holds at least 3:1 contrast on the paper (#f1f2f0). */
export const VISIT_COLORS = ["#121416", "#b42d1c", "#1f3f8a", "#2f6430", "#8a5a06", "#7a3a6a", "#3f5f73", "#6b4a2b"];
export const visitColor = (index: number) => VISIT_COLORS[((index % VISIT_COLORS.length) + VISIT_COLORS.length) % VISIT_COLORS.length];

/** One colour per detector D1..D6. */
export const DET_COLORS: Record<number, string> = {
  1: "#1f3f8a",
  2: "#2f6430",
  3: "#8a5a06",
  4: "#b42d1c",
  5: "#7a3a6a",
  6: "#121416",
};
export const detColor = (d: number) => DET_COLORS[d] ?? "#121416";

/** Plotly cannot read CSS variables, so resolve the loaded UI and typewriter faces from the document. */
function fontStacks(): { ui: string; type: string } {
  const fallbackUi = "Public Sans, ui-sans-serif, system-ui, sans-serif";
  const fallbackType = "Courier Prime, ui-monospace, monospace";
  if (typeof document === "undefined") return { ui: fallbackUi, type: fallbackType };
  const cs = getComputedStyle(document.body);
  const type = cs.getPropertyValue("--font-type").trim();
  return { ui: cs.fontFamily || fallbackUi, type: type ? `${type}, ui-monospace, monospace` : fallbackType };
}

/** Fallback SPHEREx detector coverage in µm (used only if the spectrum channel grid is empty). */
export const FALLBACK_DET_RANGES: Record<number, [number, number]> = {
  1: [0.75, 1.09],
  2: [1.09, 1.63],
  3: [1.63, 2.42],
  4: [2.42, 3.82],
  5: [3.82, 4.42],
  6: [4.42, 5.0],
};

export const TRANSPARENT = "rgba(0,0,0,0)";

export function axisBase(title: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
  const f = fontStacks();
  return {
    title: { text: title, font: { size: 12, color: PALETTE.muted, family: f.ui }, standoff: 6 },
    gridcolor: PALETTE.grid,
    zerolinecolor: PALETTE.axis,
    linecolor: PALETTE.axis,
    ticks: "outside",
    tickcolor: PALETTE.axis,
    tickfont: { size: 12, color: PALETTE.ink, family: f.type },
    automargin: true,
    ...extra,
  };
}

export function baseLayout(extra: Record<string, unknown> = {}): Record<string, unknown> {
  const f = fontStacks();
  return {
    paper_bgcolor: TRANSPARENT,
    plot_bgcolor: PALETTE.paper,
    font: { color: PALETTE.ink, size: 12, family: f.ui },
    margin: { l: 52, r: 10, t: 22, b: 44 },
    autosize: true,
    hovermode: "closest",
    hoverlabel: { bgcolor: PALETTE.paper, bordercolor: PALETTE.ink, font: { color: PALETTE.ink, size: 12, family: f.type } },
    legend: {
      orientation: "h",
      y: -0.2,
      x: 0,
      font: { size: 12, color: PALETTE.ink, family: f.ui },
      bgcolor: TRANSPARENT,
    },
    ...extra,
  };
}

export const plotConfig = {
  displaylogo: false,
  responsive: true,
  displayModeBar: "hover",
  modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines", "hoverClosestCartesian", "hoverCompareCartesian"],
};

export function mjdToIso(mjd: number): string {
  return new Date((mjd - 40587) * 86400000).toISOString();
}

export function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
