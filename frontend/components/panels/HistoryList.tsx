"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Classification, Confidence, HistoryItem } from "@/lib/types";
import { listInvestigations } from "@/lib/api";
import { formatDec, formatRA } from "@/lib/format";
import { ClassificationBadge, ConfidenceBadge, EmptyState, toArray } from "./shared";

interface Entry {
  id: string;
  name?: string | null;
  ra: number;
  dec: number;
  fov: number;
  at: string;
  source: "server" | "browser";
  classification?: Classification | null;
  confidence?: Confidence | null;
}

const LABEL: Partial<Record<Classification, string>> = {
  insufficient_data: "Insufficient data",
  likely_artifact: "Likely artifact",
  solar_system_object: "Solar-system object",
  known_high_pm_star: "Known high-PM star",
  known_variable: "Known variable",
  known_no_change: "Known, no change",
  no_significant_change: "No significant change",
  unexplained_needs_review: "Unexplained, needs review",
  low_confidence_change: "Low-confidence change",
};

/** Read-only view of what this browser remembers (keys written by the viewer page). */
function readLocal(): Entry[] {
  const out: Entry[] = [];
  for (const key of ["astra.history", "astra.recent.v1"]) {
    try {
      const raw = window.localStorage.getItem(key);
      if (!raw) continue;
      const arr: unknown = JSON.parse(raw);
      if (!Array.isArray(arr)) continue;
      for (const r of arr as Record<string, unknown>[]) {
        const ra = Number(r?.ra);
        const dec = Number(r?.dec);
        if (!Number.isFinite(ra) || !Number.isFinite(dec)) continue;
        out.push({
          id: String(r.id ?? `${ra.toFixed(4)}_${dec.toFixed(4)}`),
          name: typeof r.name === "string" ? r.name : null,
          ra,
          dec,
          fov: Number.isFinite(Number(r.fov_arcmin ?? r.fov)) ? Number(r.fov_arcmin ?? r.fov) : 3,
          at: String(r.at ?? r.created_at ?? ""),
          source: "browser",
        });
      }
    } catch {
      /* storage unavailable or malformed: ignore */
    }
  }
  return out;
}

function href(e: Entry): string {
  const q = new URLSearchParams({ ra: e.ra.toFixed(5), dec: e.dec.toFixed(5), fov: String(e.fov) });
  if (e.name) q.set("name", e.name);
  return `/investigate?${q.toString()}`;
}

export default function HistoryList() {
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [serverDown, setServerDown] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const local = readLocal();
      let server: Entry[] = [];
      let down = false;
      try {
        server = toArray<HistoryItem>(await listInvestigations(20)).map((h) => ({
          id: h.id,
          name: h.name,
          ra: h.ra,
          dec: h.dec,
          fov: h.fov_arcmin,
          at: h.created_at,
          source: "server" as const,
          classification: h.classification,
          confidence: h.confidence,
        }));
      } catch {
        down = true;
      }
      // Server entries win; drop browser duplicates by id or by (ra, dec, fov).
      const seen = new Set<string>();
      const key = (e: Entry) => `${e.ra.toFixed(3)}|${e.dec.toFixed(3)}|${e.fov}`;
      const merged: Entry[] = [];
      for (const e of [...server, ...local]) {
        if (seen.has(e.id) || seen.has(key(e))) continue;
        seen.add(e.id);
        seen.add(key(e));
        merged.push(e);
      }
      merged.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
      if (!cancelled) {
        setEntries(merged);
        setServerDown(down);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (entries === null) return <p role="status" className="text-xs text-[#8a97b4]">Loading recent investigations…</p>;

  return (
    <div>
      {serverDown && (
        <p className="mb-2 text-xs text-[#f2b84b]">
          The ASTRA service could not be reached; showing only investigations remembered in this browser.
        </p>
      )}
      {entries.length === 0 ? (
        <EmptyState title="No recent investigations">Search for a target or open a demo target to start one.</EmptyState>
      ) : (
        <ul className="divide-y divide-[#1d2742] rounded-sm border border-[#1d2742] bg-[#111830]">
          {entries.map((e) => (
            <li key={`${e.source}-${e.id}`}>
              <Link
                href={href(e)}
                className="flex flex-col gap-1 px-3 py-2.5 hover:bg-[#74c7da]/5 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[#74c7da]"
              >
                <span className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span className="text-sm font-medium text-[#e6ebf5]">{e.name || "Unnamed position"}</span>
                  <span className="text-xs text-[#8a97b4]">
                    {e.at ? e.at.slice(0, 16).replace("T", " ") : ""} {e.source === "browser" ? "· this browser" : ""}
                  </span>
                </span>
                <span className="text-xs tabular-nums text-[#8a97b4]">
                  {formatRA(e.ra)} {formatDec(e.dec)} · {e.fov}′ field
                </span>
                {(e.classification || e.confidence) && (
                  <span className="flex flex-wrap items-center gap-2">
                    {e.confidence && <ConfidenceBadge confidence={e.confidence} />}
                    {e.classification && (
                      <ClassificationBadge classification={e.classification} label={LABEL[e.classification] ?? e.classification} />
                    )}
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
