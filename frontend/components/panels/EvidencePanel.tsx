"use client";

import type { Evidence, EvidenceItem } from "@/lib/types";
import { Card, ClassificationBadge, ConfidenceBadge, NoveltyChip, sigfig } from "./shared";

const VERDICT: Record<
  EvidenceItem["verdict"],
  { icon: string; text: string; cls: string; sr: string }
> = {
  supports: { icon: "✔", text: "text-[#59d98e]", cls: "border-[#59d98e]/40 bg-[#59d98e]/10", sr: "Supports" },
  weakens: { icon: "✖", text: "text-[#f26b6b]", cls: "border-[#f26b6b]/40 bg-[#f26b6b]/10", sr: "Weakens" },
  neutral: { icon: "–", text: "text-[#8a97b4]", cls: "border-[#1d2742] bg-transparent", sr: "Neutral" },
  unavailable: { icon: "?", text: "text-[#8a97b4]", cls: "border-dashed border-[#8a97b4]/50 bg-transparent", sr: "Unavailable" },
};

function formatValue(item: EvidenceItem): string {
  const v = item.value;
  if (v === null || v === undefined) return "—";
  const s = typeof v === "number" ? sigfig(v, 3) : v;
  return item.unit ? `${s} ${item.unit}` : s;
}

function ItemRow({ item }: { item: EvidenceItem }) {
  const m = VERDICT[item.verdict] ?? VERDICT.neutral;
  const prov = item.provenance ?? [];
  return (
    <li className="border-b border-[#1d2742]/70 last:border-0">
      <details className="group">
        <summary className="flex cursor-pointer list-none items-start gap-2 py-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#5ad1e6] [&::-webkit-details-marker]:hidden">
          <span
            className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${m.cls} ${m.text}`}
          >
            <span aria-hidden>{m.icon}</span>
            <span className="sr-only">{m.sr}</span>
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <span className="text-sm font-medium text-[#e6ebf5]">{item.label}</span>
              <span className="text-sm tabular-nums text-[#e6ebf5]">{formatValue(item)}</span>
            </span>
            <span className="mt-0.5 flex flex-wrap items-center justify-between gap-x-3 text-xs text-[#8a97b4]">
              <span>{item.threshold ? `Threshold: ${item.threshold}` : "No threshold"}</span>
              <span className="text-[#5ad1e6] group-open:hidden">Why? ▸</span>
              <span className="hidden text-[#5ad1e6] group-open:inline">Hide ▾</span>
            </span>
          </span>
        </summary>
        <div className="mb-2 ml-7 space-y-1.5 rounded-md bg-[#0a0f1c]/70 px-3 py-2 text-xs leading-relaxed text-[#c3cde3]">
          <p>{item.explanation}</p>
          {prov.length > 0 && (
            <details className="text-[#8a97b4]">
              <summary className="cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#5ad1e6]">
                Provenance ({prov.length})
              </summary>
              <p className="mt-1 break-all font-mono text-[11px]">{prov.join(", ")}</p>
            </details>
          )}
        </div>
      </details>
    </li>
  );
}

export default function EvidencePanel({ evidence, title }: { evidence: Evidence; title?: string }) {
  const items = evidence.items ?? [];
  return (
    <Card title={title ?? "Evidence"}>
      <div className="flex flex-col gap-2">
        <ConfidenceBadge confidence={evidence.confidence} reason={evidence.confidence_reason} />
        <div className="flex flex-wrap items-center gap-2">
          <ClassificationBadge classification={evidence.classification} label={evidence.classification_label} />
          <NoveltyChip novelty={evidence.novelty} />
          <span className="text-xs text-[#8a97b4]">
            <span className="font-semibold text-[#59d98e]">{evidence.supports}</span> support ·{" "}
            <span className="font-semibold text-[#f26b6b]">{evidence.weakens}</span> weaken
          </span>
        </div>
        <p className="text-sm leading-relaxed text-[#e6ebf5]">{evidence.summary}</p>

        <details className="rounded-md border border-[#1d2742] bg-[#0a0f1c]/60 px-3 py-2 text-xs leading-relaxed text-[#8a97b4]">
          <summary className="cursor-pointer font-medium text-[#5ad1e6] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#5ad1e6]">
            What does this mean?
          </summary>
          <div className="mt-2 space-y-1.5">
            <p>
              The <strong className="text-[#e6ebf5]">confidence tier</strong> is set by simple, published rules applied to
              the checks below. It is <strong className="text-[#e6ebf5]">not a probability</strong>: nothing here says
              “x % likely to be real”. The reason line says which rule fired.
            </p>
            <ul className="list-inside list-disc space-y-0.5">
              <li>
                <span className="text-[#8a97b4]">Insufficient</span>: too few visits, too faint, or nothing measurable.
              </li>
              <li>
                <span className="text-[#f2b84b]">Low</span>: measurable, but several checks disagree.
              </li>
              <li>
                <span className="text-[#5ad1e6]">Moderate</span>: reasonably bright and at most one check weakens it.
              </li>
              <li>
                <span className="text-[#59d98e]">Strong</span>: bright, repeated, and no check weakens it.
              </li>
            </ul>
            <p>
              A <span className="text-[#59d98e]">✔</span> supports the classification, a <span className="text-[#f26b6b]">✖</span>{" "}
              weakens it, – is neutral, and ? means the data needed for the check were unavailable. Open any row to see the
              plain-language reason and the exposures it came from. A catalog association is never proof of identity.
            </p>
          </div>
        </details>
      </div>

      {items.length === 0 ? (
        <p className="mt-3 text-xs text-[#8a97b4]">No evidence items were produced.</p>
      ) : (
        <ul className="mt-3">
          {items.map((it) => (
            <ItemRow key={it.id} item={it} />
          ))}
        </ul>
      )}
    </Card>
  );
}
