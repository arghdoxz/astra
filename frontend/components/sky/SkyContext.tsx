"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { CatalogMatch, Grid, Investigation } from "@/lib/types";
import { Card, EmptyState, Note, num } from "@/components/panels/shared";

/**
 * Aladin Lite (v3.8) calls used here — verified against node_modules/aladin-lite/dist/aladin.js:
 *   const A = (await import("aladin-lite")).default; await A.init;
 *   const aladin = A.aladin(htmlElement, { survey, fov, target, ... });
 *   aladin.gotoRaDec(ra, dec); aladin.setFoV(deg); aladin.setBaseImageLayer("CDS/P/...");
 *   aladin.addCatalog(A.catalog({name, shape, color, sourceSize})); cat.addSources([A.marker(ra, dec, {popupTitle, popupDesc, useMarkerDefaultIcon:false}, data)]);
 *   const ov = A.graphicOverlay({name, color, lineWidth, lineDash}); ov.add(A.polyline([[ra,dec],...]) | A.polygon(...) | A.circle(ra, dec, radiusDeg, {...}));
 *   aladin.addOverlay(ov); aladin.removeOverlays();
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
type AladinLib = any;
type AladinInstance = any;
/* eslint-enable @typescript-eslint/no-explicit-any */

// `url` is the IRSA mirror of each CDS HiPS (stable during CDS outages); `id` is kept for the external Aladin link.
const IRSA_HIPS = "https://irsa.ipac.caltech.edu/data/hips/CDS";
const SURVEYS: { id: string; url: string; label: string }[] = [
  { id: "CDS/P/DSS2/color", url: `${IRSA_HIPS}/DSS2/color`, label: "DSS2 colour (optical)" },
  { id: "CDS/P/2MASS/color", url: `${IRSA_HIPS}/2MASS/Color`, label: "2MASS colour (near-IR)" },
  { id: "CDS/P/allWISE/color", url: `${IRSA_HIPS}/AllWISE/RGB-W4-W2-W1`, label: "AllWISE colour (mid-IR)" },
];
const surveyUrl = (id: string) => SURVEYS.find((s) => s.id === id)?.url ?? id;

const LAYERS = [
  { key: "fov", label: "SPHEREx field", swatch: "#74c7da", dashed: true },
  { key: "track", label: "Predicted track", swatch: "#e6ebf5", dashed: true },
  { key: "gaia", label: "Gaia matches", swatch: "#74c7da", dashed: false },
  { key: "simbad", label: "SIMBAD matches", swatch: "#f2b84b", dashed: false },
  { key: "cands", label: "Field candidates", swatch: "#e05bd1", dashed: false },
] as const;
type LayerKey = (typeof LAYERS)[number]["key"];

function esc(s: unknown): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Inverse TAN projection for a pixel of the common grid (0-based x,y; east left, north up). */
function gridPixToSky(grid: Grid, x: number, y: number): [number, number] {
  const k = grid.cdelt_arcsec / 3600;
  const xi = (-(x + 1 - grid.crpix[0]) * k * Math.PI) / 180; // toward east
  const eta = (((y + 1 - grid.crpix[1]) * k) * Math.PI) / 180; // toward north
  const ra0 = (grid.crval[0] * Math.PI) / 180;
  const dec0 = (grid.crval[1] * Math.PI) / 180;
  const rho = Math.hypot(xi, eta);
  if (rho === 0) return [grid.crval[0], grid.crval[1]];
  const c = Math.atan(rho);
  const dec = Math.asin(Math.cos(c) * Math.sin(dec0) + (eta * Math.sin(c) * Math.cos(dec0)) / rho);
  const ra = ra0 + Math.atan2(xi * Math.sin(c), rho * Math.cos(dec0) * Math.cos(c) - eta * Math.sin(dec0) * Math.sin(c));
  return [((((ra * 180) / Math.PI) % 360) + 360) % 360, (dec * 180) / Math.PI];
}

function matchPopup(m: CatalogMatch, svc: string): { title: string; desc: string } {
  const rows: string[] = [`separation from target position: ${num(m.sep_arcsec, 1)}″`];
  if (m.mag !== null && m.mag !== undefined) rows.push(`mag: ${num(m.mag, 2)}${m.mag_band ? ` (${esc(m.mag_band)})` : ""}`);
  if (m.otype) rows.push(`type: ${esc(m.otype)}`);
  if (m.pm_ra !== null && m.pm_ra !== undefined)
    rows.push(`PM: ${num(m.pm_ra, 1)}, ${num(m.pm_dec, 1)} mas/yr`);
  rows.push("an association, not proof of identity");
  return { title: `${esc(svc)}: ${esc(m.id)}`, desc: rows.join("<br/>") };
}

export default function SkyContext({
  inv,
  selectedVisit,
}: {
  inv: Investigation;
  selectedVisit?: string | null;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const instRef = useRef<{ A: AladinLib; aladin: AladinInstance } | null>(null);
  const appliedSurvey = useRef<string>(SURVEYS[0].id);
  const [status, setStatus] = useState<"loading" | "ready" | "failed">("loading");
  const [failMsg, setFailMsg] = useState("");
  const [survey, setSurvey] = useState(SURVEYS[0].id);
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>({
    fov: true,
    track: true,
    gaia: true,
    simbad: true,
    cands: true,
  });

  const ra = inv.request.ra;
  const dec = inv.request.dec;
  const fovArcmin = inv.request.fov_arcmin;
  const viewFovDeg = Math.max(3 * fovArcmin, 6) / 60;
  const surveyRef = useRef(survey);
  useEffect(() => {
    surveyRef.current = survey;
  }, [survey]);

  const webUrl = useMemo(
    () =>
      `https://aladin.cds.unistra.fr/AladinLite/?target=${encodeURIComponent(`${ra.toFixed(5)} ${dec >= 0 ? "+" : ""}${dec.toFixed(5)}`)}&fov=${viewFovDeg.toFixed(4)}&survey=${encodeURIComponent(survey)}`,
    [ra, dec, viewFovDeg, survey],
  );

  /* 1. Create the Aladin view (browser only, dynamic import). */
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;
    setStatus("loading");
    (async () => {
      try {
        const mod = await import("aladin-lite");
        const A: AladinLib = mod.default ?? mod;
        await A.init;
        if (cancelled || !hostRef.current) return;
        const el = document.createElement("div");
        el.style.width = "100%";
        el.style.height = "100%";
        host.replaceChildren(el);
        const aladin: AladinInstance = A.aladin(el, {
          survey: surveyUrl(surveyRef.current),
          fov: viewFovDeg,
          target: `${ra} ${dec}`,
          cooFrame: "ICRS",
          projection: "TAN",
          showReticle: false,
          showLayersControl: false,
          showSimbadPointerControl: false,
          showCooGridControl: false,
          showSettingsControl: false,
          showShareControl: false,
          showProjectionControl: false,
          showContextMenu: false,
          showFullscreenControl: true,
          showFrame: false,
          showZoomControl: true,
          showStatusBar: true,
          log: false,
          samp: false,
        });
        aladin.gotoRaDec(ra, dec);
        aladin.setFoV(viewFovDeg);
        appliedSurvey.current = surveyRef.current;
        instRef.current = { A, aladin };
        setStatus("ready");
      } catch (e) {
        if (cancelled) return;
        setFailMsg(typeof e === "string" ? e : e instanceof Error ? e.message : "unknown error");
        setStatus("failed");
      }
    })();
    return () => {
      cancelled = true;
      instRef.current = null;
      host.replaceChildren();
    };
  }, [ra, dec, viewFovDeg]);

  /* 2. HiPS background. */
  useEffect(() => {
    const inst = instRef.current;
    if (status !== "ready" || !inst || appliedSurvey.current === survey) return;
    try {
      inst.aladin.setBaseImageLayer(surveyUrl(survey));
      appliedSurvey.current = survey;
    } catch {
      /* keep previous survey */
    }
  }, [status, survey]);

  /* 3. Overlays (rebuilt when data, selected visit or layer toggles change). */
  useEffect(() => {
    const inst = instRef.current;
    if (status !== "ready" || !inst) return;
    const { A, aladin } = inst;
    try {
      aladin.removeOverlays();

      // Target position (resolved/requested).
      const tgt = A.catalog({ name: "Target", shape: "cross", color: "#e6ebf5", sourceSize: 18 });
      aladin.addCatalog(tgt);
      tgt.addSources([
        A.marker(inv.target.ra, inv.target.dec, {
          popupTitle: esc(inv.target.name ?? inv.request.name ?? "Target"),
          popupDesc: "requested / resolved position",
          useMarkerDefaultIcon: false,
        }),
      ]);

      if (layers.fov && inv.grid) {
        const g = inv.grid;
        const corners: [number, number][] = [
          gridPixToSky(g, -0.5, -0.5),
          gridPixToSky(g, g.width - 0.5, -0.5),
          gridPixToSky(g, g.width - 0.5, g.height - 0.5),
          gridPixToSky(g, -0.5, g.height - 0.5),
        ];
        const ov = A.graphicOverlay({ name: "SPHEREx field", color: "#74c7da", lineWidth: 1.5, lineDash: [6, 4] });
        aladin.addOverlay(ov);
        ov.add(A.polygon(corners));
      }

      const track = inv.track ?? [];
      if (layers.track && track.length > 0) {
        const ov = A.graphicOverlay({ name: "Predicted track", color: "#e6ebf5", lineWidth: 2, lineDash: [3, 3] });
        aladin.addOverlay(ov);
        if (track.length >= 2) ov.add(A.polyline(track.map((p) => [p.ra, p.dec])));
        const v = selectedVisit ? inv.visits.find((x) => x.id === selectedVisit) : undefined;
        const pts = v ? track.filter((p) => p.mjd >= v.mjd_start - 0.6 && p.mjd <= v.mjd_end + 0.6) : [];
        for (const p of pts.slice(0, 1)) ov.add(A.circle(p.ra, p.dec, 6 / 3600, { color: "#ffffff", lineWidth: 2 }));
        if (track.length === 1) {
          const m = A.catalog({ name: "Predicted position", shape: "plus", color: "#e6ebf5", sourceSize: 14 });
          aladin.addCatalog(m);
          m.addSources([A.marker(track[0].ra, track[0].dec, { popupTitle: "Predicted position", popupDesc: "", useMarkerDefaultIcon: false })]);
        }
      }

      const addMatches = (key: LayerKey, svc: string, matches: CatalogMatch[], shape: string, color: string, size: number) => {
        if (!layers[key] || matches.length === 0) return;
        const cat = A.catalog({ name: svc, shape, color, sourceSize: size });
        aladin.addCatalog(cat);
        cat.addSources(
          matches.map((m) => {
            const p = matchPopup(m, svc);
            return A.marker(m.ra, m.dec, { popupTitle: p.title, popupDesc: p.desc, useMarkerDefaultIcon: false });
          }),
        );
      };
      addMatches("gaia", "Gaia DR3", inv.crossmatch?.gaia?.matches ?? [], "circle", "#74c7da", 12);
      addMatches("simbad", "SIMBAD", inv.crossmatch?.simbad?.matches ?? [], "square", "#f2b84b", 16);

      if (layers.cands && (inv.candidates ?? []).length > 0) {
        const cat = A.catalog({ name: "Candidates", shape: "circle", color: "#e05bd1", sourceSize: 20 });
        aladin.addCatalog(cat);
        cat.addSources(
          inv.candidates.map((c) =>
            A.marker(c.ra, c.dec, {
              popupTitle: `Candidate ${esc(c.id)} (${c.kind === "dipole" ? "possible mover" : "brightness change"})`,
              popupDesc: `peak Z ${num(c.peak_z, 1)}<br/>${esc(c.evidence.classification_label)}<br/>needs review — not a confirmed object`,
              useMarkerDefaultIcon: false,
            }),
          ),
        );
      }
    } catch (e) {
      // A drawing error should never take the page down.
      console.warn("SkyContext overlay error", e);
    }
  }, [status, inv, selectedVisit, layers]);

  const toggleLayer = (k: LayerKey) => setLayers((p) => ({ ...p, [k]: !p[k] }));

  return (
    <Card
      title="Sky context"
      subtitle={`Centred on the target, ${(viewFovDeg * 60).toFixed(0)}′ across`}
      right={
        <label className="flex items-center gap-1.5 text-xs text-[#8a97b4]">
          <span>Survey</span>
          <select
            value={survey}
            onChange={(e) => setSurvey(e.target.value)}
            className="rounded-sm border border-[#1d2742] bg-[#0a0f1c] px-2 py-1 text-xs text-[#e6ebf5] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#74c7da]"
            aria-label="Background survey"
          >
            {SURVEYS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      }
    >
      {status === "failed" ? (
        <EmptyState title="Sky map could not be loaded" tone="warn">
          <p>
            The interactive sky viewer needs WebGL2 and could not start here{failMsg ? ` (${failMsg})` : ""}. The target is at
            RA {ra.toFixed(5)}°, Dec {dec.toFixed(5)}°.
          </p>
          <p className="mt-2">
            <a
              href={webUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-[#74c7da] underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#74c7da]"
            >
              Open this position in Aladin Lite on the web ↗
            </a>
          </p>
        </EmptyState>
      ) : (
        <div className="relative">
          <div
            ref={hostRef}
            className="h-[320px] w-full overflow-hidden rounded-sm border border-[#1d2742] bg-[#0a0f1c] sm:h-[420px]"
            role="region"
            aria-label="Sky map around the target"
          />
          {status === "loading" && (
            <div
              role="status"
              className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs text-[#8a97b4]"
            >
              Loading sky map…
            </div>
          )}
        </div>
      )}

      <fieldset className="mt-2">
        <legend className="sr-only">Overlays</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {LAYERS.map((l) => (
            <label key={l.key} className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-[#8a97b4]">
              <input
                type="checkbox"
                checked={layers[l.key]}
                onChange={() => toggleLayer(l.key)}
                className="h-3.5 w-3.5"
                style={{ accentColor: l.swatch }}
                disabled={status === "failed"}
              />
              <span
                aria-hidden
                className="inline-block h-0 w-4 border-t-2"
                style={{ borderColor: l.swatch, borderStyle: l.dashed ? "dashed" : "solid" }}
              />
              {l.label}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="mt-2 space-y-1.5">
        <Note>
          Background survey imagery is for context — <strong className="text-[#e6ebf5]">not SPHEREx data</strong>. Catalog
          markers are associations at their listed separation, not proof of identity.
          {selectedVisit && inv.track.length > 0 ? ` White ring: predicted position during ${selectedVisit}.` : ""}
        </Note>
      </div>
    </Card>
  );
}
