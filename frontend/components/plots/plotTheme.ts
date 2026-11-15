// Shared dark observatory theme for Plotly charts (no plotly import here).

export const PALETTE = {
  bg: "#0a0f1c",
  card: "#111830",
  border: "#1d2742",
  text: "#e6ebf5",
  muted: "#8a97b4",
  cyan: "#5ad1e6",
  amber: "#f2b84b",
  green: "#59d98e",
  red: "#f26b6b",
  magenta: "#e05bd1",
};

/** One colour per visit (colour-blind-friendly-ish, distinct on dark). */
export const VISIT_COLORS = ["#5ad1e6", "#f2b84b", "#e05bd1", "#59d98e", "#8fa8ff", "#f2866b", "#c79bff", "#e6ebf5"];
export const visitColor = (index: number) => VISIT_COLORS[((index % VISIT_COLORS.length) + VISIT_COLORS.length) % VISIT_COLORS.length];

/** One colour per detector D1..D6. */
export const DET_COLORS: Record<number, string> = {
  1: "#8fa8ff",
  2: "#5ad1e6",
  3: "#59d98e",
  4: "#f2b84b",
  5: "#f2866b",
  6: "#e05bd1",
};
export const detColor = (d: number) => DET_COLORS[d] ?? "#e6ebf5";

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
  return {
    title: { text: title, font: { size: 11, color: PALETTE.muted }, standoff: 6 },
    gridcolor: PALETTE.border,
    zerolinecolor: PALETTE.border,
    linecolor: PALETTE.border,
    tickfont: { size: 10, color: PALETTE.muted },
    automargin: true,
    ...extra,
  };
}

export function baseLayout(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    paper_bgcolor: TRANSPARENT,
    plot_bgcolor: TRANSPARENT,
    font: { color: PALETTE.text, size: 11 },
    margin: { l: 52, r: 10, t: 22, b: 44 },
    autosize: true,
    hovermode: "closest",
    hoverlabel: { bgcolor: PALETTE.card, bordercolor: PALETTE.border, font: { color: PALETTE.text, size: 11 } },
    legend: {
      orientation: "h",
      y: -0.2,
      x: 0,
      font: { size: 10, color: PALETTE.muted },
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
