"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiFailure, getInvestigation, resolveTarget, startInvestigation } from "@/lib/api";
import { demoForCoords, demoForName } from "@/lib/demoFallback";
import type { Investigation } from "@/lib/types";

export type Phase = "idle" | "resolving" | "starting" | "polling" | "done" | "error";

export interface LoadError {
  title: string;
  message: string;
  code?: string;
}

export interface InvestigationState {
  inv: Investigation | null;
  phase: Phase;
  error: LoadError | null;
  /** Set when a precomputed demo bundle was loaded instead of a live result. */
  fallback: { reason: string } | null;
  /** Human-readable status while no investigation object exists yet. */
  note: string;
}

interface Params {
  ra?: number;
  dec?: number;
  fov: number;
  name?: string;
  dets?: number[];
}

interface Run {
  cancelled: boolean;
  key: string;
  keys: Set<string>;
}

const INITIAL: InvestigationState = { inv: null, phase: "idle", error: null, fallback: null, note: "" };

function makeKey(p: Params): string {
  if (p.ra === undefined || p.dec === undefined) return `name:${p.name ?? ""}|${p.fov}|${(p.dets ?? []).join(",")}`;
  return `${p.ra.toFixed(5)}|${p.dec.toFixed(5)}|${p.fov}|${(p.dets ?? []).join(",")}`;
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function friendly(e: unknown): LoadError {
  if (e instanceof ApiFailure) {
    if (e.code === "network" || e.code === "timeout") {
      return {
        title: "The ASTRA service is not reachable",
        message:
          "The live backend did not respond. Free hosting can take up to a minute to wake up, so please retry shortly. Precomputed snapshots of real data are available for library targets that have one (see Targets).",
        code: e.code,
      };
    }
    if (e.code === "not_found") return { title: "Target not found", message: e.message, code: e.code };
    return { title: "The investigation could not be completed", message: e.message, code: e.code };
  }
  return { title: "Something went wrong", message: e instanceof Error ? e.message : "Unknown error." };
}

/**
 * Drives an investigation from URL parameters: resolve (if only a name is given) -> start -> poll every 1.5 s,
 * with a precomputed-bundle fallback near the five demo targets. `onCoords` is called when a name was resolved so the
 * page can write ra/dec into the URL; that URL change does NOT restart the run.
 */
export function useInvestigation(
  params: Params,
  onCoords?: (ra: number, dec: number, name?: string) => void,
): InvestigationState & { retry: () => void } {
  const key = makeKey(params);
  const [st, setSt] = useState<{ key: string } & InvestigationState>({ key: "", ...INITIAL });
  const [nonce, setNonce] = useState(0);
  const runRef = useRef<Run | null>(null);
  const cb = useRef(onCoords);
  const paramsRef = useRef(params);
  useEffect(() => {
    cb.current = onCoords;
    paramsRef.current = params;
  });

  useEffect(() => {
    const existing = runRef.current;
    if (existing && !existing.cancelled && existing.keys.has(key)) return; // our own URL update
    if (existing) existing.cancelled = true;
    const run: Run = { cancelled: false, key, keys: new Set([key]) };
    runRef.current = run;
    void execute(run, { ...paramsRef.current });

    async function execute(run: Run, p: Params) {
      const set = (patch: Partial<InvestigationState>) => {
        if (run.cancelled) return;
        setSt((prev) => ({ ...prev, key: run.key, ...patch }));
      };
      setSt({ key: run.key, ...INITIAL, phase: "starting", note: "Preparing investigation…" });

      let ra = p.ra;
      let dec = p.dec;
      let name = p.name;

      const loadBundleFallback = async (reason: string): Promise<boolean> => {
        if (ra === undefined || dec === undefined) return false;
        const bundle = await demoForCoords(ra, dec);
        if (!bundle || run.cancelled) return false;
        set({ inv: bundle, phase: "done", error: null, fallback: { reason }, note: "" });
        return true;
      };

      if (ra === undefined || dec === undefined) {
        if (!name) {
          set({ phase: "idle" });
          return;
        }
        set({ phase: "resolving", note: `Resolving “${name}”…` });
        try {
          const r = await resolveTarget(name);
          if (run.cancelled) return;
          ra = r.ra;
          dec = r.dec;
          name = r.name ?? name;
        } catch (e) {
          if (run.cancelled) return;
          const offline = !(e instanceof ApiFailure) || e.code === "network" || e.code === "timeout";
          if (offline) {
            const d = await demoForName(name);
            if (run.cancelled) return;
            if (d) {
              ra = d.ra;
              dec = d.dec;
              name = d.name;
              cb.current?.(ra, dec, name);
              if (d.bundle) {
                set({ inv: d.bundle, phase: "done", fallback: { reason: "The live service could not be reached." }, error: null, note: "" });
                return;
              }
            }
          }
          set({ phase: "error", error: friendly(e) });
          return;
        }
        const nk = makeKey({ ...p, ra, dec, name });
        run.keys.add(nk);
        run.key = nk;
        cb.current?.(ra, dec, name);
      }

      if (ra === undefined || dec === undefined) return;
      const raN: number = ra;
      const decN: number = dec;
      set({ phase: "starting", note: "Starting investigation…" });
      const fail = async (e: unknown) => {
        if (run.cancelled) return;
        const fe = friendly(e);
        if (await loadBundleFallback(fe.title + ". " + (e instanceof ApiFailure && e.code !== "network" && e.code !== "timeout" ? e.message : "Showing a precomputed snapshot instead."))) return;
        set({ phase: "error", error: fe });
      };

      try {
        const started = await startInvestigation({
          ra: raN,
          dec: decN,
          fov_arcmin: p.fov,
          name,
          detectors: p.dets ?? [1, 2, 3, 4, 5, 6],
          propagate_pm: true,
        });
        if (run.cancelled) return;
        let fails = 0;
        while (!run.cancelled) {
          try {
            const inv = await getInvestigation(started.id);
            if (run.cancelled) return;
            fails = 0;
            if (inv.status === "done") {
              set({ inv, phase: "done", error: null, fallback: null, note: "" });
              return;
            }
            if (inv.status === "error") {
              set({ inv });
              await fail(new ApiFailure(inv.error?.code ?? "investigation_failed", inv.error?.message ?? "The investigation failed."));
              return;
            }
            set({ inv, phase: "polling", note: "" });
          } catch (e) {
            fails += 1;
            if (fails >= 3) {
              await fail(e);
              return;
            }
          }
          await sleep(1500);
        }
      } catch (e) {
        await fail(e);
      }
    }
  }, [key, nonce]);

  // cancel on unmount
  useEffect(() => {
    return () => {
      if (runRef.current) runRef.current.cancelled = true;
    };
  }, []);

  const retry = useCallback(() => {
    if (runRef.current) runRef.current.cancelled = true;
    runRef.current = null;
    setNonce((n) => n + 1);
  }, []);

  const view = st.key === key ? st : { key, ...INITIAL, phase: "starting" as Phase, note: "Preparing investigation…" };
  return { inv: view.inv, phase: view.phase, error: view.error, fallback: view.fallback, note: view.note, retry };
}
