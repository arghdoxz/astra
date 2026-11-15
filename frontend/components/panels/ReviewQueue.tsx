"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { Classification, ReviewItem } from "@/lib/types";
import { API_BASE, listReviewQueue } from "@/lib/api";
import { formatDec, formatRA } from "@/lib/format";
import { ClassificationBadge, ConfidenceBadge, EmptyState, ErrorNote, btn, errMessage, toArray } from "./shared";

const LABEL: Record<Classification, string> = {
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

const KIND: Record<ReviewItem["kind"], string> = {
  dipole: "Possible mover (dipole)",
  monopole: "Brightness change (monopole)",
  target: "Requested target",
};

function link(it: ReviewItem): string {
  const q = new URLSearchParams({ ra: it.ra.toFixed(5), dec: it.dec.toFixed(5), fov: "3" });
  if (it.name) q.set("name", it.name);
  if (it.kind === "target") {
    q.set("tab", "evidence");
  } else {
    q.set("cand", it.candidate_id.split(":").slice(1).join(":") || it.candidate_id);
    q.set("tab", "candidates");
  }
  return `/investigate?${q.toString()}`;
}

function thumb(url: string): string {
  return /^https?:\/\//i.test(url) ? url : `${API_BASE}${url.startsWith("/") ? "" : "/"}${url}`;
}

export default function ReviewQueue() {
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    setItems(null);
    try {
      setItems(toArray<ReviewItem>(await listReviewQueue(50)));
    } catch (e) {
      setError(errMessage(e));
      setItems([]);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    listReviewQueue(50)
      .then((r) => {
        if (!cancelled) setItems(toArray<ReviewItem>(r));
      })
      .catch((e) => {
        if (!cancelled) {
          setError(errMessage(e));
          setItems([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (items === null) return <p role="status" className="text-xs text-[#8a97b4]">Loading the review queue…</p>;

  if (error) {
    return (
      <div className="space-y-2">
        <ErrorNote>The review queue could not be loaded: {error}</ErrorNote>
        <p className="text-xs text-[#8a97b4]">
          The queue lives on the ASTRA service. If it is starting up or offline, try again in a minute.
        </p>
        <button type="button" className={btn} onClick={() => void load()}>
          Try again
        </button>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState title="Nothing to review yet">
        Candidates and targets from live investigations appear here so that people can mark them real, artifact, known or
        unsure. Run an investigation to add the first one.
      </EmptyState>
    );
  }

  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((it) => {
        const t: Record<string, number> = it.tally ?? {};
        return (
          <li key={it.candidate_id} className="overflow-hidden rounded-lg border border-[#1d2742] bg-[#111830]">
            <Link
              href={link(it)}
              className="flex h-full flex-col focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[#5ad1e6]"
            >
              <div className="flex aspect-[2/1] w-full items-center justify-center bg-[#0a0f1c]">
                {it.thumbnail_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={thumb(it.thumbnail_url)}
                    alt={`Cutout for ${it.name ?? it.candidate_id}`}
                    loading="lazy"
                    className="h-full w-full object-contain"
                    style={{ imageRendering: "pixelated" }}
                  />
                ) : (
                  <span className="text-xs text-[#8a97b4]">no thumbnail</span>
                )}
              </div>
              <div className="flex flex-1 flex-col gap-1.5 p-3">
                <p className="text-sm font-medium text-[#e6ebf5]">
                  {it.name || "Unnamed position"} <span className="font-mono text-xs text-[#8a97b4]">{it.candidate_id.split(":").pop()}</span>
                </p>
                <p className="text-xs text-[#8a97b4]">
                  {KIND[it.kind] ?? it.kind} · <span className="tabular-nums">{formatRA(it.ra)} {formatDec(it.dec)}</span>
                </p>
                <div className="flex flex-wrap items-center gap-1.5">
                  <ConfidenceBadge confidence={it.confidence} />
                  <ClassificationBadge classification={it.classification} label={LABEL[it.classification] ?? it.classification} />
                </div>
                <p className="mt-auto pt-1 text-xs text-[#8a97b4]">
                  Verdicts: real <b className="text-[#59d98e]">{t.real ?? 0}</b> · artifact <b className="text-[#f58a8a]">{t.artifact ?? 0}</b> · known{" "}
                  <b className="text-[#5ad1e6]">{t.known ?? 0}</b> · unsure <b className="text-[#c3cde3]">{t.unsure ?? 0}</b>
                </p>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
