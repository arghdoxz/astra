import type { Detector } from "@/lib/types";

export type PlayerMode = "visits" | "exposures" | "blink" | "diff" | "stack";
export type DiffMethod = "simple" | "psf_matched";
export type TabId = "evidence" | "motion" | "brightness" | "spectrum" | "candidates" | "catalogs" | "ai" | "provenance";

export const PLAYER_MODES: PlayerMode[] = ["visits", "exposures", "blink", "diff", "stack"];
export const TAB_IDS: TabId[] = ["evidence", "motion", "brightness", "spectrum", "candidates", "catalogs", "ai", "provenance"];

export interface InvestigateParams {
  ra?: number;
  dec?: number;
  fov: number;
  name?: string;
  /** Player detector. undefined = auto (best available). */
  det?: Detector;
  /** Detectors requested for the investigation (subset of 1..6). undefined = all. */
  dets?: number[];
  mode: PlayerMode;
  visit?: string;
  /** Second visit for blink / diff. */
  vb?: string;
  method: DiffMethod;
  cand?: string;
  tab?: TabId;
}

interface ParamSource {
  get(name: string): string | null;
}

function num(v: string | null): number | undefined {
  if (v == null || v.trim() === "") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

export function parseInvestigateParams(sp: ParamSource): InvestigateParams {
  const ra = num(sp.get("ra"));
  const dec = num(sp.get("dec"));
  let fov = num(sp.get("fov")) ?? 3;
  fov = Math.min(12, Math.max(1, fov));
  const detRaw = sp.get("det");
  let det: Detector | undefined;
  if (detRaw === "all") det = "all";
  else {
    const d = num(detRaw);
    if (d && Number.isInteger(d) && d >= 1 && d <= 6) det = d;
  }
  const detsRaw = sp.get("dets");
  let dets: number[] | undefined;
  if (detsRaw) {
    const arr = detsRaw
      .split(",")
      .map((x) => Number(x))
      .filter((x) => Number.isInteger(x) && x >= 1 && x <= 6);
    if (arr.length) dets = Array.from(new Set(arr)).sort();
  }
  const modeRaw = sp.get("mode") as PlayerMode | null;
  const tabRaw = sp.get("tab") as TabId | null;
  const methodRaw = sp.get("method");
  return {
    ra: ra !== undefined && ra >= 0 && ra < 360 ? ra : undefined,
    dec: dec !== undefined && dec >= -90 && dec <= 90 ? dec : undefined,
    fov,
    name: sp.get("name")?.trim() || undefined,
    det,
    dets,
    mode: modeRaw && PLAYER_MODES.includes(modeRaw) ? modeRaw : "visits",
    visit: sp.get("visit") || undefined,
    vb: sp.get("vb") || undefined,
    method: methodRaw === "psf_matched" ? "psf_matched" : "simple",
    cand: sp.get("cand") || undefined,
    tab: tabRaw && TAB_IDS.includes(tabRaw) ? tabRaw : undefined,
  };
}

function round(x: number, d: number): number {
  const f = 10 ** d;
  return Math.round(x * f) / f;
}

/** Serialise to a query string (defaults are omitted to keep shared URLs short). */
export function buildInvestigateQuery(p: Partial<InvestigateParams>): string {
  const q = new URLSearchParams();
  if (p.ra !== undefined) q.set("ra", String(round(p.ra, 5)));
  if (p.dec !== undefined) q.set("dec", String(round(p.dec, 5)));
  if (p.fov !== undefined) q.set("fov", String(p.fov));
  if (p.name) q.set("name", p.name);
  if (p.det !== undefined) q.set("det", String(p.det));
  if (p.dets && p.dets.length && p.dets.length < 6) q.set("dets", p.dets.join(","));
  if (p.mode && p.mode !== "visits") q.set("mode", p.mode);
  if (p.visit) q.set("visit", p.visit);
  if (p.vb) q.set("vb", p.vb);
  if (p.method && p.method !== "simple") q.set("method", p.method);
  if (p.cand) q.set("cand", p.cand);
  if (p.tab) q.set("tab", p.tab);
  return q.toString();
}

export function investigateHref(p: Partial<InvestigateParams>, base = "/investigate"): string {
  const qs = buildInvestigateQuery(p);
  return qs ? `${base}?${qs}` : base;
}
