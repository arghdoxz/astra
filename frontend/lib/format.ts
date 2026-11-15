import type { Detector } from "@/lib/types";

export const DETECTOR_RANGES: Record<number, [number, number]> = {
  1: [0.75, 1.09],
  2: [1.09, 1.62],
  3: [1.62, 2.42],
  4: [2.42, 3.82],
  5: [3.82, 4.42],
  6: [4.42, 5.0],
};

export function detectorLabel(d: Detector): string {
  if (d === "all") return "All-IR (display only)";
  const r = DETECTOR_RANGES[d];
  return r ? `D${d} · ${r[0].toFixed(2)}–${r[1].toFixed(2)} µm` : `D${d}`;
}

export function detectorShort(d: Detector): string {
  return d === "all" ? "All-IR" : `D${d}`;
}

export function fmtNum(x: number | null | undefined, digits = 2): string {
  if (x == null || !Number.isFinite(x)) return "—";
  if (x !== 0 && Math.abs(x) < 10 ** -digits) return x.toExponential(1);
  return x.toFixed(digits);
}

/** Flux in µJy with 1σ uncertainty. */
export function fmtFlux(flux: number | null | undefined, err?: number | null): string {
  if (flux == null || !Number.isFinite(flux)) return "—";
  const d = Math.abs(flux) >= 100 ? 0 : Math.abs(flux) >= 10 ? 1 : 2;
  const base = `${flux.toFixed(d)}`;
  return err != null && Number.isFinite(err) ? `${base} ± ${err.toFixed(d)} µJy` : `${base} µJy`;
}

function pad(n: number, w = 2): string {
  return String(n).padStart(w, "0");
}

/** 8h55m10.83s style, input degrees. */
export function formatRA(deg: number, decimals = 2): string {
  const h = (((deg % 360) + 360) % 360) / 15;
  let hh = Math.floor(h);
  const m = (h - hh) * 60;
  let mm = Math.floor(m);
  let s = (m - mm) * 60;
  const f = 10 ** decimals;
  s = Math.round(s * f) / f;
  if (s >= 60) { s -= 60; mm += 1; }
  if (mm >= 60) { mm -= 60; hh += 1; }
  if (hh >= 24) hh -= 24;
  return `${pad(hh)}h${pad(mm)}m${pad(Math.floor(s))}${decimals ? "." + s.toFixed(decimals).split(".")[1] : ""}s`;
}

export function formatDec(deg: number, decimals = 1): string {
  const sign = deg < 0 ? "−" : "+";
  const a = Math.abs(deg);
  let dd = Math.floor(a);
  const m = (a - dd) * 60;
  let mm = Math.floor(m);
  let s = (m - mm) * 60;
  const f = 10 ** decimals;
  s = Math.round(s * f) / f;
  if (s >= 60) { s -= 60; mm += 1; }
  if (mm >= 60) { mm -= 60; dd += 1; }
  return `${sign}${pad(dd)}°${pad(mm)}′${pad(Math.floor(s))}${decimals ? "." + s.toFixed(decimals).split(".")[1] : ""}″`;
}

export function fmtCoordsDeg(ra: number, dec: number, digits = 5): string {
  return `${ra.toFixed(digits)}, ${dec.toFixed(digits)}`;
}

export function mjdToDate(mjd: number): Date {
  return new Date((mjd - 40587) * 86400000);
}

export function mjdToISODate(mjd: number): string {
  const d = mjdToDate(mjd);
  return Number.isFinite(d.getTime()) ? d.toISOString().slice(0, 10) : "—";
}

export function mjdToISO(mjd: number): string {
  const d = mjdToDate(mjd);
  return Number.isFinite(d.getTime()) ? d.toISOString().slice(0, 16).replace("T", " ") + " UT" : "—";
}

export function isoDateOnly(iso: string | null | undefined): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

/** Great-circle-ish separation in arcmin (small-angle, fine for matching). */
export function sepArcmin(ra1: number, dec1: number, ra2: number, dec2: number): number {
  const d2r = Math.PI / 180;
  const dra = (((ra1 - ra2 + 540) % 360) - 180) * Math.cos(((dec1 + dec2) / 2) * d2r);
  const ddec = dec1 - dec2;
  return Math.hypot(dra, ddec) * 60;
}

/**
 * Parse a coordinate string: decimal degrees ("133.795 -7.245") or sexagesimal
 * ("08 55 10.83 -07 14 42.5", "08h55m10.831s -7d14m42.53s"). Returns null for anything that is
 * not clearly a coordinate pair (so names like "WISE 0855-0714" fall through to name resolution).
 */
export function parseCoordinates(input: string): { ra: number; dec: number } | null {
  const s = input.trim().replace(/−/g, "-");
  if (!s || !/^[\s\d+\-.,:hmsdHMSD°′″'"]+$/.test(s)) return null;
  const cleaned = s.replace(/[hmsdHMSD°′″'":,]/g, " ");
  const tokens = cleaned.match(/[+-]?\d+(?:\.\d+)?|[+-]?\.\d+/g);
  if (!tokens) return null;
  const num = (t: string) => parseFloat(t);
  let ra: number, dec: number;
  if (tokens.length === 2) {
    ra = num(tokens[0]);
    dec = num(tokens[1]);
  } else if (tokens.length === 6) {
    const hh = num(tokens[0]), hm = num(tokens[1]), hs = num(tokens[2]);
    if (hh < 0 || hm < 0 || hs < 0 || hm >= 60 || hs >= 60) return null;
    ra = (hh + hm / 60 + hs / 3600) * 15;
    const neg = tokens[3].startsWith("-");
    const dd = Math.abs(num(tokens[3])), dm = num(tokens[4]), ds = num(tokens[5]);
    if (dm < 0 || ds < 0 || dm >= 60 || ds >= 60) return null;
    dec = (neg ? -1 : 1) * (dd + dm / 60 + ds / 3600);
  } else {
    return null;
  }
  if (!Number.isFinite(ra) || !Number.isFinite(dec)) return null;
  if (ra < 0 || ra >= 360 || dec < -90 || dec > 90) return null;
  return { ra, dec };
}
