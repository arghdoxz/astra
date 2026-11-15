"use client";

import type { Investigation } from "@/lib/types";
import { Card, ClassificationBadge, ConfidenceBadge, EmptyState, num } from "./shared";

export const KIND_LABEL: Record<"dipole" | "monopole", string> = {
  dipole: "Dipole: possible mover",
  monopole: "Monopole: brightness change",
};

export default function CandidateList({
  inv,
  selectedId,
  onSelect,
}: {
  inv: Investigation;
  selectedId?: string | null;
  onSelect: (id: string) => void;
}) {
  const cands = inv.candidates ?? [];
  return (
    <Card
      title="Field change candidates"
      subtitle="Other sources in the field whose brightness or position changed between visits"
    >
      {cands.length === 0 ? (
        <EmptyState title="No field change candidates passed the thresholds">
          <p>
            This is a valid result, not a failure: nothing else in the field changed by more than 5σ in a way that
            repeated across detectors or visit pairs. Difference images of crowded or saturated stars often show
            residuals that are deliberately rejected here.
          </p>
        </EmptyState>
      ) : (
        <ul className="space-y-2">
          {cands.map((c) => {
            const weak = (c.evidence?.items ?? []).filter((i) => i.verdict === "weakens");
            const sel = c.id === selectedId;
            return (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => onSelect(c.id)}
                  aria-pressed={sel}
                  className={`w-full rounded-sm border p-2.5 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#74c7da] ${
                    sel ? "border-[#74c7da]/70 bg-[#74c7da]/10" : "border-[#1d2742] bg-[#0a0f1c]/60 hover:border-[#74c7da]/40"
                  }`}
                >
                  <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="font-mono text-sm font-semibold text-[#e6ebf5]">{c.id}</span>
                    <span className="text-xs text-[#e6ebf5]">{KIND_LABEL[c.kind]}</span>
                    <span className="text-xs tabular-nums text-[#8a97b4]">peak Z {num(c.peak_z, 1)}</span>
                    <span className="text-xs text-[#8a97b4]">
                      {c.detectors.map((d) => `D${d}`).join(", ") || "—"}
                    </span>
                    <span className="text-xs text-[#8a97b4]">
                      {c.visit_pairs.map(([a, b]) => `${a}→${b}`).join(", ") || "—"}
                    </span>
                  </span>
                  <span className="mt-1.5 flex flex-wrap items-center gap-2">
                    <ConfidenceBadge confidence={c.evidence.confidence} />
                    <ClassificationBadge classification={c.evidence.classification} label={c.evidence.classification_label} />
                  </span>
                  {weak.length > 0 && (
                    <span className="mt-1.5 block text-xs text-[#f58a8a]">
                      <span className="font-semibold">Reasons for doubt:</span> {weak.map((w) => w.label).join("; ")}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
