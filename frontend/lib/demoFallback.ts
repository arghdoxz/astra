import type { Investigation } from "@/lib/types";
import { TARGETS, findTargetByName } from "@/lib/targets";
import { sepArcmin } from "@/lib/format";
import { normalizeInvestigation } from "@/lib/api";

export interface DemoIndexItem {
  slug: string;
  name: string;
  ra: number;
  dec: number;
  fov_arcmin: number;
}

/** Challenge-text coordinates of WISE 0855 (~2010 position): matched within 4 arcmin so the coordinate trap still works offline. */
const WISE_CHALLENGE = { ra: 133.79513, dec: -7.24515, slug: "wise-0855", radiusArcmin: 4 };

let indexPromise: Promise<DemoIndexItem[]> | null = null;

export function loadDemoIndex(): Promise<DemoIndexItem[]> {
  if (!indexPromise) {
    indexPromise = fetch("/demo/index.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("no index"))))
      .then((j) => (Array.isArray(j) ? (j as DemoIndexItem[]) : ((j?.items ?? []) as DemoIndexItem[])))
      .catch(() => {
        indexPromise = null; // allow a retry later
        // static index missing: fall back to the built-in library
        return TARGETS.map((t) => ({ slug: t.slug, name: t.name, ra: t.ra, dec: t.dec, fov_arcmin: t.fov_arcmin }));
      });
  }
  return indexPromise;
}

/** Find the demo target within 1 arcmin of (ra, dec), or the WISE 0855 challenge coordinates within 4 arcmin. */
export async function findDemoTarget(ra: number, dec: number): Promise<DemoIndexItem | null> {
  const idx = await loadDemoIndex();
  let best: { item: DemoIndexItem; sep: number } | null = null;
  for (const it of idx) {
    const sep = sepArcmin(ra, dec, it.ra, it.dec);
    if (sep <= 1 && (!best || sep < best.sep)) best = { item: it, sep };
  }
  if (best) return best.item;
  if (sepArcmin(ra, dec, WISE_CHALLENGE.ra, WISE_CHALLENGE.dec) <= WISE_CHALLENGE.radiusArcmin) {
    return idx.find((i) => i.slug === WISE_CHALLENGE.slug) ?? null;
  }
  return null;
}

/** Load a bundle; returns null when the bundle does not exist (yet). */
export async function loadDemoBundle(slug: string): Promise<Investigation | null> {
  try {
    const r = await fetch(`/demo/${slug}/investigation.json`);
    if (!r.ok) return null;
    const inv = (await r.json()) as Investigation;
    if (!inv || typeof inv !== "object" || !inv.id) return null;
    return normalizeInvestigation(inv);
  } catch {
    return null;
  }
}

export async function demoForCoords(ra: number, dec: number): Promise<Investigation | null> {
  const t = await findDemoTarget(ra, dec);
  return t ? loadDemoBundle(t.slug) : null;
}

/** Offline name lookup, e.g. when /api/resolve is unreachable. */
export async function demoForName(
  name: string,
): Promise<{ bundle: Investigation | null; ra: number; dec: number; name: string } | null> {
  const t = findTargetByName(name);
  if (!t) return null;
  return { bundle: await loadDemoBundle(t.slug), ra: t.ra, dec: t.dec, name: t.name };
}
