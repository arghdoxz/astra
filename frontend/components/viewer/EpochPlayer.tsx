"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import type { Candidate, Detector, Exposure, Frame, Investigation, Visit } from "@/lib/types";
import { assetUrl, isLive } from "@/lib/api";
import { detectorLabel, detectorShort, mjdToISODate } from "@/lib/format";
import type { DiffMethod, PlayerMode } from "@/lib/url";
import { skyToGrid } from "@/components/viewer/wcs";

/* ------------------------------------------------------------------ image cache */

type Loaded = { img: HTMLImageElement; tainted: boolean } | "error";
const imageCache = new Map<string, Loaded>();
const pending = new Map<string, Promise<Loaded>>();

function isCrossOrigin(url: string): boolean {
  try {
    return new URL(url, window.location.href).origin !== window.location.origin;
  } catch {
    return false;
  }
}

/** Load a PNG frame. Tries CORS-enabled first (so we can read pixels for the display LUT); if that fails on a cross-origin URL, retries without CORS (pixels unreadable => LUT disabled). */
function loadFrame(url: string): Promise<Loaded> {
  const hit = imageCache.get(url);
  if (hit) return Promise.resolve(hit);
  const inflight = pending.get(url);
  if (inflight) return inflight;
  const p = new Promise<Loaded>((resolve) => {
    const finish = (v: Loaded) => {
      if (imageCache.size > 400) {
        const first = imageCache.keys().next().value;
        if (first !== undefined) imageCache.delete(first);
      }
      imageCache.set(url, v);
      pending.delete(url);
      resolve(v);
    };
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => finish({ img, tainted: false });
    img.onerror = () => {
      if (!isCrossOrigin(url)) return finish("error");
      const img2 = new Image();
      img2.onload = () => finish({ img: img2, tainted: true });
      img2.onerror = () => finish("error");
      img2.src = url;
    };
    img.src = url;
  });
  pending.set(url, p);
  return p;
}

/* ------------------------------------------------------------------ frame selection */

interface Item {
  key: string;
  label: string;
  mjd: number;
  visitId?: string;
  obsId?: string;
  detector: Detector;
  url: string | null;
  frame: Frame | null;
  gray: boolean; // false for Z-maps (coloured)
  missing: string; // reason shown when url is null
  exposure?: Exposure;
}

function fk(kind: string, visitId: string | null | undefined, visitB: string | null | undefined, obsId: string | null | undefined, method: string | null | undefined, det: Detector): string {
  return [kind, visitId ?? "", visitB ?? "", obsId ?? "", kind === "diff" ? (method ?? "simple") : "", String(det)].join("|");
}

const MODE_LABELS: Record<PlayerMode, string> = {
  visits: "Visit stacks",
  exposures: "Exposures",
  blink: "Blink A/B",
  diff: "Difference",
  stack: "Single stack",
};
const MODE_HELP: Record<PlayerMode, string> = {
  visits: "Animate the stacked image of each ~6-month visit",
  exposures: "Animate single exposures of this detector, in time order",
  blink: "Alternate between two visits to spot changes by eye",
  diff: "Z-map of visit B minus visit A",
  stack: "One visit stack, no animation",
};

export interface EpochPlayerProps {
  inv: Investigation;
  detector: Detector;
  onDetectorChange: (d: Detector) => void;
  mode: PlayerMode;
  onModeChange: (m: PlayerMode) => void;
  visitId?: string;
  onVisitChange?: (id: string) => void;
  exposureFilter?: string[] | null;
  selectedCandidate?: Candidate | null;
  diffMethod: DiffMethod;
  onDiffMethodChange: (m: DiffMethod) => void;
  /** Second visit for blink / diff (defaults to the latest visit). */
  visitB?: string;
  onVisitBChange?: (id: string) => void;
  /** Called whenever the displayed frame changes (used to place the timeline marker). */
  onFrameChange?: (info: { mjd: number; visitId?: string }) => void;
  /** Hide the secondary controls (embed). */
  compact?: boolean;
}

interface Overlays { track: boolean; measured: boolean; candidates: boolean; flags: boolean; crosshair: boolean }

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 24;

export default function EpochPlayer({
  inv,
  detector,
  onDetectorChange,
  mode,
  onModeChange,
  visitId,
  onVisitChange,
  exposureFilter,
  selectedCandidate,
  diffMethod,
  onDiffMethodChange,
  visitB,
  onVisitBChange,
  onFrameChange,
  compact = false,
}: EpochPlayerProps) {
  const grid = inv.grid;
  const hasGrid = grid !== null;
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [fps, setFps] = useState(2);
  const [tick, setTick] = useState(0);
  const [overlays, setOverlays] = useState<Overlays>({ track: true, measured: true, candidates: true, flags: false, crosshair: true });
  const [bright, setBright] = useState(0);
  const [contrast, setContrast] = useState(1);
  const [gamma, setGamma] = useState(1);
  const [view, setView] = useState({ zoom: 1, panX: 0, panY: 0 });
  const [size, setSize] = useState({ w: 0, h: 0 });

  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const offRef = useRef<HTMLCanvasElement | null>(null);
  const lastImgRef = useRef<{ src: CanvasImageSource; w: number; h: number } | null>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{ dist: number } | null>(null);
  const frameCb = useRef(onFrameChange);
  useEffect(() => {
    frameCb.current = onFrameChange;
  });

  /* ---------------------------------------------------------- frame index & items */
  const visits = useMemo<Visit[]>(() => [...inv.visits].sort((a, b) => a.mjd_mean - b.mjd_mean), [inv.visits]);
  const frameIndex = useMemo(() => {
    const m = new Map<string, Frame>();
    for (const f of inv.frames) m.set(fk(f.kind, f.visit_id, f.visit_b, f.obs_id, f.method, f.detector), f);
    return m;
  }, [inv.frames]);
  const detectorsWithData = useMemo(() => {
    const s = new Set<string>();
    for (const f of inv.frames) s.add(String(f.detector));
    return s;
  }, [inv.frames]);

  const visitA: Visit | undefined = visits.find((v) => v.id === visitId) ?? (mode === "stack" ? visits[visits.length - 1] : visits[0]);
  const visitBObj: Visit | undefined = (() => {
    const b = visits.find((v) => v.id === visitB);
    if (b && b.id !== visitA?.id) return b;
    const last = visits[visits.length - 1];
    if (last && last.id !== visitA?.id) return last;
    return visits.find((v) => v.id !== visitA?.id);
  })();

  const items = useMemo<Item[]>(() => {
    const det = detector;
    const stackItem = (v: Visit): Item => {
      const f = frameIndex.get(fk("visit_stack", v.id, null, null, null, det)) ?? null;
      return {
        key: `s:${v.id}:${det}`,
        label: v.date_label,
        mjd: v.mjd_mean,
        visitId: v.id,
        detector: det,
        url: f ? assetUrl(inv, f.url) : null,
        frame: f,
        gray: true,
        missing: `No data for ${detectorShort(det)} in this visit`,
      };
    };
    switch (mode) {
      case "visits":
        return visits.map(stackItem);
      case "stack":
        return visitA ? [stackItem(visitA)] : [];
      case "blink":
        return [visitA, visitBObj].filter((v): v is Visit => !!v).map(stackItem);
      case "diff": {
        if (!visitA || !visitBObj) return [];
        const f = frameIndex.get(fk("diff", visitA.id, visitBObj.id, null, diffMethod, det)) ?? null;
        let url: string | null = f ? assetUrl(inv, f.url) : null;
        // Live difference maps are rendered on demand by the API even if not listed in `frames`.
        if (!url && isLive(inv)) {
          url = assetUrl(inv, `/api/investigations/${encodeURIComponent(inv.id)}/diff/${visitA.id}/${visitBObj.id}/${det}.png?method=${diffMethod}`);
        }
        return [
          {
            key: `d:${visitA.id}:${visitBObj.id}:${det}:${diffMethod}`,
            label: `${visitBObj.date_label} − ${visitA.date_label}`,
            mjd: visitBObj.mjd_mean,
            visitId: visitBObj.id,
            detector: det,
            url,
            frame: f,
            gray: false,
            missing: `No difference map for ${detectorShort(det)} between these visits`,
          },
        ];
      }
      case "exposures": {
        const sel = inv.exposures
          .filter((e) => (exposureFilter ? exposureFilter.includes(e.obs_id) : det !== "all" && e.detector === det))
          .sort((a, b) => a.mjd - b.mjd);
        return sel.map((e): Item => {
          const f = frameIndex.get(fk("exposure", null, null, e.obs_id, null, e.detector)) ?? null;
          const bad = e.status !== "ok";
          return {
            key: `e:${e.obs_id}:${e.detector}`,
            label: e.date_obs,
            mjd: e.mjd,
            visitId: e.visit_id,
            obsId: e.obs_id,
            detector: e.detector,
            url: f && !bad ? assetUrl(inv, f.url) : null,
            frame: f,
            gray: true,
            missing: bad ? `Exposure ${e.status} — no frame for ${detectorShort(e.detector)}` : `No data for ${detectorShort(e.detector)} in this exposure`,
            exposure: e,
          };
        });
      }
    }
  }, [mode, detector, visits, visitA, visitBObj, frameIndex, inv, diffMethod, exposureFilter]);

  const n = items.length;
  const animated = (mode === "visits" || mode === "exposures" || mode === "blink") && n > 1;
  const isPlaying = playing && animated;

  // In "visits" mode the URL-driven visitId is the source of truth while paused.
  const controlled = mode === "visits" && visitId ? items.findIndex((i) => i.visitId === visitId) : -1;
  const curIdx = Math.max(0, Math.min(n - 1, !isPlaying && controlled >= 0 ? controlled : idx));
  const item: Item | null = n ? items[curIdx] : null;

  const goTo = useCallback(
    (i: number) => {
      if (!n) return;
      const j = ((i % n) + n) % n;
      setIdx(j);
      if (mode === "visits" && items[j].visitId) onVisitChange?.(items[j].visitId as string);
    },
    [n, mode, items, onVisitChange],
  );

  function togglePlay() {
    if (!animated) return;
    if (isPlaying) {
      setPlaying(false);
      if (mode === "visits" && item?.visitId) onVisitChange?.(item.visitId);
    } else {
      setIdx(curIdx);
      setPlaying(true);
    }
  }

  // animation clock
  useEffect(() => {
    if (!isPlaying) return;
    const t = setInterval(() => setIdx((i) => (Math.min(i, n - 1) + 1) % n), 1000 / fps);
    return () => clearInterval(t);
  }, [isPlaying, fps, n]);

  // report current frame upward
  const itemMjd = item?.mjd;
  const itemVisit = item?.visitId;
  useEffect(() => {
    if (itemMjd !== undefined) frameCb.current?.({ mjd: itemMjd, visitId: itemVisit });
  }, [itemMjd, itemVisit]);

  /* ---------------------------------------------------------- flags overlay frame */
  const flagsUrl = useMemo(() => {
    if (!item || !overlays.flags) return null;
    const vid = item.visitId;
    if (!vid) return null;
    const f = frameIndex.get(fk("flags", vid, null, null, null, item.detector));
    return f ? assetUrl(inv, f.url) : null;
  }, [item, overlays.flags, frameIndex, inv]);

  /* ---------------------------------------------------------- preloading */
  useEffect(() => {
    let cancelled = false;
    const urls: string[] = [];
    for (let k = 0; k < Math.min(4, n); k++) {
      const u = items[(curIdx + k) % n]?.url;
      if (u) urls.push(u);
    }
    if (flagsUrl) urls.push(flagsUrl);
    for (const u of urls) {
      if (imageCache.has(u)) continue;
      loadFrame(u).then(() => {
        if (!cancelled) setTick((t) => t + 1);
      });
    }
    return () => {
      cancelled = true;
    };
  }, [items, curIdx, n, flagsUrl]);

  /* ---------------------------------------------------------- canvas size */
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setSize({ w: Math.round(r.width), h: Math.round(r.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [hasGrid]);

  /* ---------------------------------------------------------- LUT */
  const lut = useMemo(() => {
    const l = new Uint8ClampedArray(256);
    for (let i = 0; i < 256; i++) {
      let v = (i / 255 - 0.5) * contrast + 0.5 + bright;
      v = Math.min(1, Math.max(0, v));
      l[i] = Math.round(Math.pow(v, 1 / gamma) * 255);
    }
    return l;
  }, [bright, contrast, gamma]);
  const lutActive = bright !== 0 || contrast !== 1 || gamma !== 1;

  /* ---------------------------------------------------------- drawing */
  const loadedNow = item?.url ? imageCache.get(item.url) : undefined;
  const flagsLoaded = flagsUrl ? imageCache.get(flagsUrl) : undefined;
  const taintedNow = loadedNow && loadedNow !== "error" ? loadedNow.tainted : false;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !grid || size.w < 4 || size.h < 4) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    const W = size.w;
    const H = size.h;
    if (canvas.width !== Math.round(W * dpr) || canvas.height !== Math.round(H * dpr)) {
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
    }
    const ctx = canvas.getContext("2d");
    const sans = getComputedStyle(canvas).fontFamily || "system-ui, sans-serif";
    const mono = "ui-monospace, Menlo, Consolas, monospace";
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#05070d";
    ctx.fillRect(0, 0, W, H);
    ctx.imageSmoothingEnabled = false;

    const gw = grid.width;
    const gh = grid.height;
    const fit = Math.min(W / gw, H / gh);
    const sc = fit * view.zoom;
    const left = W / 2 - (gw * sc) / 2 + view.panX;
    const top = H / 2 - (gh * sc) / 2 + view.panY;
    const rw = gw * sc;
    const rh = gh * sc;
    const gx = (x: number) => left + (x + 0.5) * sc;
    const gy = (y: number) => top + (gh - 1 - y + 0.5) * sc; // canvasY = height - 1 - y

    // --- image or placeholder
    let drewImage = false;
    let message: string | null = null;
    if (!item) {
      message = "No frames available for this selection";
    } else if (!item.url) {
      message = item.missing;
    } else {
      const loaded = imageCache.get(item.url);
      if (loaded === "error") {
        message = "Frame could not be loaded";
      } else if (loaded) {
        const img = loaded.img;
        let src: CanvasImageSource = img;
        if (item.gray && lutActive && !loaded.tainted) {
          try {
            let off = offRef.current;
            if (!off) off = offRef.current = document.createElement("canvas");
            off.width = img.naturalWidth;
            off.height = img.naturalHeight;
            const octx = off.getContext("2d", { willReadFrequently: true });
            if (octx) {
              octx.drawImage(img, 0, 0);
              const data = octx.getImageData(0, 0, off.width, off.height);
              const px = data.data;
              for (let i = 0; i < px.length; i += 4) {
                px[i] = lut[px[i]];
                px[i + 1] = lut[px[i + 1]];
                px[i + 2] = lut[px[i + 2]];
              }
              octx.putImageData(data, 0, 0);
              src = off;
            }
          } catch {
            src = img;
          }
        }
        ctx.drawImage(src, left, top, rw, rh);
        lastImgRef.current = { src, w: rw, h: rh };
        drewImage = true;
      } else if (lastImgRef.current) {
        // still loading: keep the previous frame on screen (no flicker during playback)
        ctx.globalAlpha = 0.5;
        ctx.drawImage(lastImgRef.current.src, left, top, rw, rh);
        ctx.globalAlpha = 1;
      }
    }

    if (drewImage && flagsLoaded && flagsLoaded !== "error") {
      ctx.globalAlpha = 0.55;
      ctx.drawImage(flagsLoaded.img, left, top, rw, rh);
      ctx.globalAlpha = 1;
    }

    // frame outline
    ctx.strokeStyle = "rgba(138,151,180,0.35)";
    ctx.lineWidth = 1;
    ctx.setLineDash([]);
    ctx.strokeRect(left + 0.5, top + 0.5, rw, rh);

    const center = { x: W / 2, y: H / 2 };
    if (message) {
      ctx.fillStyle = "#0a0f1c";
      ctx.fillRect(left, top, rw, rh);
      ctx.setLineDash([6, 5]);
      ctx.strokeStyle = "rgba(138,151,180,0.45)";
      ctx.strokeRect(left + 0.5, top + 0.5, rw, rh);
      ctx.setLineDash([]);
      ctx.textAlign = "center";
      ctx.fillStyle = "#e6ebf5";
      ctx.font = `500 14px ${sans}`;
      wrapText(ctx, message, center.x, center.y - 4, Math.min(W - 40, 360), 18);
      ctx.fillStyle = "#8a97b4";
      ctx.font = `12px ${sans}`;
      ctx.fillText("Playback continues with the next frame.", center.x, center.y + 34);
    } else if (!loadedNow && item?.url) {
      ctx.textAlign = "center";
      ctx.fillStyle = "#8a97b4";
      ctx.font = `12px ${sans}`;
      ctx.fillText("Loading frame…", center.x, H - 40);
    }

    // --- overlays
    const curMjd = item?.mjd;
    // FOV crosshair at grid centre (the investigation target position)
    if (overlays.crosshair) {
      const cx = gx(grid.crpix[0] - 1);
      const cy = gy(grid.crpix[1] - 1);
      ctx.strokeStyle = "rgba(230,235,245,0.55)";
      ctx.lineWidth = 1;
      const gap = 8;
      const len = 14;
      ctx.beginPath();
      ctx.moveTo(cx - gap - len, cy); ctx.lineTo(cx - gap, cy);
      ctx.moveTo(cx + gap, cy); ctx.lineTo(cx + gap + len, cy);
      ctx.moveTo(cx, cy - gap - len); ctx.lineTo(cx, cy - gap);
      ctx.moveTo(cx, cy + gap); ctx.lineTo(cx, cy + gap + len);
      ctx.stroke();
    }

    // predicted track
    if (overlays.track && inv.track.length) {
      const pts = [...inv.track].sort((a, b) => a.mjd - b.mjd);
      ctx.strokeStyle = "rgba(116, 199, 218,0.85)";
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      pts.forEach((p, i) => (i === 0 ? ctx.moveTo(gx(p.x), gy(p.y)) : ctx.lineTo(gx(p.x), gy(p.y))));
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "rgba(116, 199, 218,0.9)";
      for (const p of pts) {
        ctx.beginPath();
        ctx.arc(gx(p.x), gy(p.y), 2.5, 0, Math.PI * 2);
        ctx.fill();
      }
      if (curMjd !== undefined) {
        let best = pts[0];
        for (const p of pts) if (Math.abs(p.mjd - curMjd) < Math.abs(best.mjd - curMjd)) best = p;
        ctx.strokeStyle = "#74c7da";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(gx(best.x), gy(best.y), 9, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = "#74c7da";
        ctx.font = `11px ${mono}`;
        ctx.textAlign = "left";
        ctx.fillText(`predicted ${mjdToISODate(best.mjd)}`, gx(best.x) + 13, gy(best.y) - 11);
      }
    }

    // measured centroids
    if (overlays.measured && inv.astrometry?.measured?.length) {
      for (const m of inv.astrometry.measured) {
        const p = skyToGrid(grid, m.ra, m.dec);
        const here = item?.visitId && m.visit_id === item.visitId;
        ctx.strokeStyle = here ? "#c58ab8" : "rgba(224,90,209,0.55)";
        ctx.lineWidth = here ? 2.5 : 1.3;
        const s = here ? 7 : 5;
        const x = gx(p.x);
        const y = gy(p.y);
        ctx.beginPath();
        ctx.moveTo(x - s, y - s); ctx.lineTo(x + s, y + s);
        ctx.moveTo(x - s, y + s); ctx.lineTo(x + s, y - s);
        ctx.stroke();
      }
    }

    // candidates
    if (overlays.candidates && inv.candidates?.length) {
      ctx.font = `11px ${mono}`;
      ctx.textAlign = "left";
      for (const c of inv.candidates) {
        const sel = selectedCandidate?.id === c.id;
        ctx.strokeStyle = sel ? "#f2b84b" : "rgba(242,184,75,0.6)";
        ctx.lineWidth = sel ? 2.5 : 1.3;
        ctx.beginPath();
        ctx.arc(gx(c.x), gy(c.y), sel ? 11 : 8, 0, Math.PI * 2);
        ctx.stroke();
        if (sel) {
          ctx.fillStyle = "#f2b84b";
          ctx.fillText(c.id, gx(c.x) + 14, gy(c.y) - 12);
        }
      }
    }

    // compass (N up, E left)
    {
      const ox = 40;
      const oy = 46;
      ctx.strokeStyle = "rgba(230,235,245,0.8)";
      ctx.fillStyle = "rgba(230,235,245,0.9)";
      ctx.lineWidth = 1.3;
      ctx.beginPath();
      ctx.moveTo(ox, oy); ctx.lineTo(ox, oy - 26);
      ctx.moveTo(ox - 4, oy - 21); ctx.lineTo(ox, oy - 26); ctx.lineTo(ox + 4, oy - 21);
      ctx.moveTo(ox, oy); ctx.lineTo(ox - 26, oy);
      ctx.moveTo(ox - 21, oy - 4); ctx.lineTo(ox - 26, oy); ctx.lineTo(ox - 21, oy + 4);
      ctx.stroke();
      ctx.font = `600 11px ${sans}`;
      ctx.textAlign = "center";
      ctx.fillText("N", ox, oy - 31);
      ctx.fillText("E", ox - 33, oy + 4);
    }

    // scale bar: 1 arcmin
    {
      const len = (60 / grid.cdelt_arcsec) * sc;
      if (len > 24 && len < W * 0.7) {
        const x0 = 14;
        const y0 = H - 16;
        ctx.strokeStyle = "rgba(230,235,245,0.9)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x0, y0); ctx.lineTo(x0 + len, y0);
        ctx.moveTo(x0, y0 - 4); ctx.lineTo(x0, y0 + 4);
        ctx.moveTo(x0 + len, y0 - 4); ctx.lineTo(x0 + len, y0 + 4);
        ctx.stroke();
        ctx.fillStyle = "rgba(230,235,245,0.9)";
        ctx.font = `11px ${mono}`;
        ctx.textAlign = "left";
        ctx.fillText("1′", x0 + len / 2 - 5, y0 - 8);
      }
    }

    // frame label (top right)
    if (item) {
      ctx.textAlign = "right";
      ctx.font = `500 12px ${mono}`;
      const label = `${mode === "diff" ? item.label : mjdToISODate(item.mjd)} · ${detectorShort(item.detector)}`;
      ctx.fillStyle = "rgba(5,7,13,0.65)";
      const tw = ctx.measureText(label).width;
      ctx.fillRect(W - tw - 20, 8, tw + 14, 22);
      ctx.fillStyle = "#e6ebf5";
      ctx.fillText(label, W - 13, 24);
    }
  }, [grid, size, view, item, tick, overlays, lut, lutActive, inv, selectedCandidate, loadedNow, flagsLoaded, mode]);

  /* ---------------------------------------------------------- zoom / pan */
  const zoomAt = useCallback(
    (factor: number, px?: number, py?: number) => {
      setView((v) => {
        const z2 = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.zoom * factor));
        const r = z2 / v.zoom;
        const cx = size.w / 2;
        const cy = size.h / 2;
        const x = px ?? cx;
        const y = py ?? cy;
        return { zoom: z2, panX: x - cx - (x - cx - v.panX) * r, panY: y - cy - (y - cy - v.panY) * r };
      });
    },
    [size.w, size.h],
  );

  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      zoomAt(Math.exp(-e.deltaY * 0.0015), e.clientX - rect.left, e.clientY - rect.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt, hasGrid]);

  function onPointerDown(e: ReactPointerEvent<HTMLCanvasElement>) {
    e.currentTarget.setPointerCapture(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 2) {
      const [a, b] = Array.from(pointers.current.values());
      gesture.current = { dist: Math.hypot(a.x - b.x, a.y - b.y) };
    }
  }
  function onPointerMove(e: ReactPointerEvent<HTMLCanvasElement>) {
    const prev = pointers.current.get(e.pointerId);
    if (!prev) return;
    const cur = { x: e.clientX, y: e.clientY };
    pointers.current.set(e.pointerId, cur);
    if (pointers.current.size === 1) {
      const dx = cur.x - prev.x;
      const dy = cur.y - prev.y;
      setView((v) => ({ ...v, panX: v.panX + dx, panY: v.panY + dy }));
    } else if (pointers.current.size === 2 && gesture.current) {
      const [a, b] = Array.from(pointers.current.values());
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      const rect = e.currentTarget.getBoundingClientRect();
      if (gesture.current.dist > 0) zoomAt(dist / gesture.current.dist, (a.x + b.x) / 2 - rect.left, (a.y + b.y) / 2 - rect.top);
      gesture.current = { dist };
    }
  }
  function onPointerUp(e: ReactPointerEvent<HTMLCanvasElement>) {
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) gesture.current = null;
  }

  function onKeyDown(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key === " " || e.key === "Spacebar") {
      e.preventDefault();
      togglePlay();
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      setPlaying(false);
      goTo(curIdx + 1);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      setPlaying(false);
      goTo(curIdx - 1);
    } else if (e.key === "+" || e.key === "=") {
      zoomAt(1.25);
    } else if (e.key === "-") {
      zoomAt(0.8);
    } else if (e.key === "0") {
      setView({ zoom: 1, panX: 0, panY: 0 });
    }
  }

  function changeMode(m: PlayerMode) {
    setPlaying(false);
    setIdx(0);
    onModeChange(m);
  }

  function resetDisplay() {
    setBright(0);
    setContrast(1);
    setGamma(1);
  }

  /* ---------------------------------------------------------- render */
  if (!grid) {
    return (
      <div className="card flex aspect-square max-h-[60vh] w-full items-center justify-center p-6 text-center text-sm text-muted">
        <div>
          <div className="mx-auto mb-3 h-5 w-5 animate-pulse rounded-full bg-accent/60" aria-hidden />
          Waiting for the pixel grid and frames… the viewer appears as soon as the first stacks are rendered.
        </div>
      </div>
    );
  }

  const visit = item?.visitId ? inv.visits.find((v) => v.id === item.visitId) : undefined;
  const expo = item?.exposure;
  const stretch = item?.frame?.stretch;
  const ariaDesc = item
    ? `${MODE_LABELS[mode]}: ${mode === "diff" ? item.label : mjdToISODate(item.mjd)}, ${detectorLabel(item.detector)}, frame ${curIdx + 1} of ${n}`
    : "No frame";

  const toggles: { key: keyof Overlays; label: string; available: boolean; reason: string }[] = [
    { key: "track", label: "Predicted track", available: inv.track.length > 0, reason: "No predicted track available" },
    { key: "measured", label: "Measured centroids", available: (inv.astrometry?.measured?.length ?? 0) > 0, reason: "No measured centroids yet" },
    { key: "candidates", label: "Candidates", available: (inv.candidates?.length ?? 0) > 0, reason: "No candidates in this field" },
    { key: "flags", label: "Flags", available: inv.frames.some((f) => f.kind === "flags"), reason: "No flag frames available" },
    { key: "crosshair", label: "FOV centre", available: true, reason: "" },
  ];

  const A = visitA;
  const B = visitBObj;

  return (
    <section className="card overflow-hidden" aria-label="Epoch player">
      <div
        ref={wrapRef}
        tabIndex={0}
        role="application"
        aria-label={`Image viewer. ${ariaDesc}. Space plays or pauses, left and right arrows step through frames, plus and minus zoom.`}
        onKeyDown={onKeyDown}
        className="relative w-full select-none bg-bg outline-offset-[-2px]"
        style={{ aspectRatio: `${grid.width} / ${grid.height}`, maxHeight: "72vh", minHeight: 240 }}
      >
        <canvas
          ref={canvasRef}
          className="absolute inset-0 h-full w-full cursor-grab active:cursor-grabbing"
          style={{ imageRendering: "pixelated", touchAction: view.zoom > 1 ? "none" : "pan-y" }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onDoubleClick={() => setView({ zoom: 1, panX: 0, panY: 0 })}
        />
        {mode === "diff" && (
          <div className="pointer-events-none absolute bottom-2 right-3 max-w-[70%] rounded bg-bg/75 px-2 py-1 text-right text-[11px] leading-tight text-fg">
            <div className="mono">Z = (B−A)/σ, ±8σ</div>
            <div className="text-muted">{diffMethod === "simple" ? "Simple subtraction" : "Gaussian PSF-matched (approximation, not ZOGY)"}</div>
          </div>
        )}
      </div>

      {/* caption */}
      <div className="border-t border-line px-3.5 py-2.5 text-xs leading-relaxed text-muted">
        {item ? (
          <>
            <div className="text-fg">
              <span className="mono">{mode === "diff" ? item.label : mjdToISODate(item.mjd)}</span>
              {visit && (
                <>
                  {" · "}visit {visit.id} ({visit.collection.replace(/^spherex_/, "").toUpperCase()})
                </>
              )}
              {" · "}
              {detectorLabel(item.detector)}
              
              {expo && (
                <>
                  {" · "}obs_id <span className="mono break-all">{expo.obs_id}</span>
                </>
              )}
              {n > 1 && (
                <>
                  {" · "}frame {curIdx + 1}/{n}
                </>
              )}
            </div>
            <div>
              {item.gray ? (
                <>
                  Stretch: {stretch?.kind ?? "asinh"}
                  {mode === "exposures" ? ", per detector" : ", shared across visits"}
                  {stretch && stretch.unit === "MJy/sr" ? ` (${stretch.vmin.toPrecision(3)}–${stretch.vmax.toPrecision(3)} MJy/sr)` : ""}
                </>
              ) : (
                <>Difference Z-map, diverging colormap clipped at ±8σ</>
              )}
              {" · "}
              {grid.cdelt_arcsec}″/px · N↑ E← · scale bar 1′
              {detector === "all" && " · All-IR stack is for display only, not photometry"}
            </div>
            {taintedNow && (
              <div className="text-warn">Brightness/contrast adjustments are unavailable for frames served without CORS headers.</div>
            )}
          </>
        ) : (
          <span>No frames for this selection.</span>
        )}
      </div>

      {/* controls */}
      <div className="space-y-2.5 border-t border-line p-3">
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn btn-sm min-w-[72px]" onClick={togglePlay} disabled={!animated} aria-label={isPlaying ? "Pause" : "Play"} title="Space">
            {isPlaying ? "❚❚ Pause" : "▶ Play"}
          </button>
          <button type="button" className="btn btn-sm" onClick={() => { setPlaying(false); goTo(curIdx - 1); }} disabled={n < 2} aria-label="Previous frame" title="←">
            ◀
          </button>
          <button type="button" className="btn btn-sm" onClick={() => { setPlaying(false); goTo(curIdx + 1); }} disabled={n < 2} aria-label="Next frame" title="→">
            ▶
          </button>
          <input
            type="range"
            min={0}
            max={Math.max(0, n - 1)}
            step={1}
            value={curIdx}
            disabled={n < 2}
            onChange={(e) => { setPlaying(false); goTo(Number(e.target.value)); }}
            aria-label="Frame scrubber"
            className="min-w-[120px] flex-1"
          />
          <label className="flex items-center gap-1.5 text-xs text-muted">
            Speed
            <input
              type="range"
              min={0.5}
              max={8}
              step={0.5}
              value={fps}
              onChange={(e) => setFps(Number(e.target.value))}
              aria-label="Playback speed in frames per second"
              className="w-20"
              disabled={!animated}
            />
            <span className="mono w-12 text-fg">{fps} fps</span>
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div role="group" aria-label="Playback mode" className="flex flex-wrap gap-1">
            {(Object.keys(MODE_LABELS) as PlayerMode[]).map((m) => (
              <button key={m} type="button" className="btn btn-sm" aria-pressed={mode === m} title={MODE_HELP[m]} onClick={() => changeMode(m)}>
                {MODE_LABELS[m]}
              </button>
            ))}
          </div>
          <div role="group" aria-label="Detector" className="flex flex-wrap gap-1">
            {[1, 2, 3, 4, 5, 6].map((d) => (
              <button
                key={d}
                type="button"
                className="btn btn-sm"
                aria-pressed={detector === d}
                title={`${detectorLabel(d)}${detectorsWithData.has(String(d)) ? "" : " — no frames in this investigation"}`}
                style={detectorsWithData.has(String(d)) ? undefined : { opacity: 0.55 }}
                onClick={() => onDetectorChange(d)}
              >
                D{d}
              </button>
            ))}
            <button
              type="button"
              className="btn btn-sm"
              aria-pressed={detector === "all"}
              title="Stack of all detectors, for display only (not photometric)"
              onClick={() => onDetectorChange("all")}
            >
              All-IR (display only)
            </button>
          </div>
        </div>

        {(mode === "blink" || mode === "diff") && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
            <label className="flex items-center gap-1.5">
              A (reference)
              <select className="input" value={A?.id ?? ""} onChange={(e) => onVisitChange?.(e.target.value)}>
                {visits.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.id} · {v.date_label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1.5">
              B
              <select className="input" value={B?.id ?? ""} onChange={(e) => onVisitBChange?.(e.target.value)}>
                {visits.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.id} · {v.date_label}
                  </option>
                ))}
              </select>
            </label>
            {mode === "diff" && (
              <div role="group" aria-label="Difference method" className="flex gap-1">
                <button type="button" className="btn btn-sm" aria-pressed={diffMethod === "simple"} onClick={() => onDiffMethodChange("simple")}>
                  Simple subtraction
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  aria-pressed={diffMethod === "psf_matched"}
                  title="Sharper stack convolved with a single Gaussian kernel. An approximation, not ZOGY or Alard–Lupton."
                  onClick={() => onDiffMethodChange("psf_matched")}
                >
                  Gaussian PSF-matched (approx.)
                </button>
              </div>
            )}
          </div>
        )}

        {!compact && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <div role="group" aria-label="Overlays" className="flex flex-wrap gap-1">
              {toggles.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  className="btn btn-sm"
                  aria-pressed={overlays[t.key] && t.available}
                  disabled={!t.available}
                  title={t.available ? undefined : t.reason}
                  onClick={() => setOverlays((o) => ({ ...o, [t.key]: !o[t.key] }))}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div role="group" aria-label="Zoom" className="flex items-center gap-1">
              <button type="button" className="btn btn-sm" onClick={() => zoomAt(0.8)} aria-label="Zoom out" title="−">
                −
              </button>
              <span className="mono w-12 text-center text-xs text-muted">{Math.round(view.zoom * 100)}%</span>
              <button type="button" className="btn btn-sm" onClick={() => zoomAt(1.25)} aria-label="Zoom in" title="+">
                +
              </button>
              <button type="button" className="btn btn-sm" onClick={() => setView({ zoom: 1, panX: 0, panY: 0 })} title="Fit frame (double-click also works)">
                Fit
              </button>
            </div>
          </div>
        )}

        {!compact && (
          <details className="text-xs text-muted">
            <summary className="cursor-pointer select-none py-1 hover:text-fg">Display: brightness, contrast, gamma</summary>
            <div className="mt-2 grid gap-2 sm:grid-cols-3">
              <label className="flex items-center gap-2">
                Brightness
                <input type="range" min={-0.5} max={0.5} step={0.01} value={bright} onChange={(e) => setBright(Number(e.target.value))} className="flex-1" />
              </label>
              <label className="flex items-center gap-2">
                Contrast
                <input type="range" min={0.3} max={3} step={0.05} value={contrast} onChange={(e) => setContrast(Number(e.target.value))} className="flex-1" />
              </label>
              <label className="flex items-center gap-2">
                Gamma
                <input type="range" min={0.3} max={3} step={0.05} value={gamma} onChange={(e) => setGamma(Number(e.target.value))} className="flex-1" />
              </label>
            </div>
            <div className="mt-2 flex items-center gap-3">
              <button type="button" className="btn btn-sm" onClick={resetDisplay} disabled={!lutActive}>
                Reset
              </button>
              <span>Applied in your browser to image frames only (not difference maps). The underlying stretch is unchanged.</span>
            </div>
          </details>
        )}
        <p className="text-[11px] text-muted">
          Click the image, then Space to play/pause, ←/→ to step, +/− to zoom, 0 to fit. Wheel or pinch to zoom, drag to pan.
        </p>
      </div>
    </section>
  );
}

function wrapText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, maxWidth: number, lineHeight: number) {
  const words = text.split(" ");
  let line = "";
  let yy = y;
  for (const w of words) {
    const test = line ? `${line} ${w}` : w;
    if (ctx.measureText(test).width > maxWidth && line) {
      ctx.fillText(line, x, yy);
      line = w;
      yy += lineHeight;
    } else {
      line = test;
    }
  }
  if (line) ctx.fillText(line, x, yy);
}
