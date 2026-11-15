"use client";

import type { Evidence, EvidenceItem } from "@/lib/types";
import { Card, ClassificationBadge, ConfidenceBadge, NoveltyChip, sigfig } from "./shared";

const VERDICT: Record<
  EvidenceItem["verdict"],
  { icon: string; text: string; cls: string; sr: string }
> = {
  supports: { icon: "✔", text: "text-good", cls: "border-good bg-panel", sr: "Supports" },
  weakens: { icon: "✖", text: "text-bad", cls: "border-bad bg-panel", sr: "Weakens" },
  neutral: { icon: "–", text: "text-muted", cls: "border-line bg-panel", sr: "Neutral" },
  unavailable: { icon: "?", text: "text-muted", cls: "border-dashed border-muted bg-panel", sr: "Unavailable" },
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
    <li className="border-b border-line last:border-0">
      <details className="group">
        <summary className="flex cursor-pointer list-none items-start gap-2 py-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-pencil [&::-webkit-details-marker]:hidden">
          <span
            className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center border text-sm font-bold ${m.cls} ${m.text}`}
          >
            <span aria-hidden>{m.icon}</span>
            <span className="sr-only">{m.sr}</span>
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <span className="text-sm font-medium text-fg">{item.label}</span>
              <span className="text-sm tabular-nums text-fg">{formatValue(item)}</span>
            </span>
            <span className="mt-0.5 flex flex-wrap items-center justify-between gap-x-3 text-sm text-muted">
              <span>{item.threshold ? `Threshold: ${item.threshold}` : "No threshold"}</span>
              <span className="text-accent group-open:hidden">Why? ▸</span>
              <span className="hidden text-accent group-open:inline">Hide ▾</span>
            </span>
          </span>
        </summary>
        <div className="mb-2 ml-7 space-y-1.5 border-l-2 border-line bg-panel2 px-3 py-2 text-sm leading-relaxed text-fg">
          <p>{item.explanation}</p>
          {prov.length > 0 && (
            <details className="text-muted">
              <summary className="cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-pencil">
                Provenance ({prov.length})
              </summary>
              <p className="mt-1 break-all mono text-sm">{prov.join(", ")}</p>
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
          <span className="text-sm text-muted">
            <span className="font-semibold text-good">{evidence.supports}</span> support ·{" "}
            <span className="font-semibold text-bad">{evidence.weakens}</span> weaken
          </span>
        </div>
        <p className="text-sm leading-relaxed text-fg">{evidence.summary}</p>

        <details className="border border-line bg-panel px-3 py-2 text-sm leading-relaxed text-muted">
          <summary className="cursor-pointer font-medium text-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-pencil">
            What does this mean?
          </summary>
          <div className="mt-2 space-y-1.5">
            <p>
              The <strong className="text-fg">confidence tier</strong> is set by simple, published rules applied to
              the checks below. It is <strong className="text-fg">not a probability</strong>: nothing here says
              “x % likely to be real”. The reason line says which rule fired.
            </p>
            <ul className="list-inside list-disc space-y-0.5">
              <li>
                <span className="text-muted">Insufficient</span>: too few visits, too faint, or nothing measurable.
              </li>
              <li>
                <span className="text-warn">Low</span>: measurable, but several checks disagree.
              </li>
              <li>
                <span className="text-accent">Moderate</span>: reasonably bright and at most one check weakens it.
              </li>
              <li>
                <span className="text-good">Strong</span>: bright, repeated, and no check weakens it.
              </li>
            </ul>
            <p>
              A <span className="text-good">✔</span> supports the classification, a <span className="text-bad">✖</span>{" "}
              weakens it, – is neutral, and ? means the data needed for the check were unavailable. Open any row to see the
              plain-language reason and the exposures it came from. A catalog association is never proof of identity.
            </p>
          </div>
        </details>
      </div>

      {items.length === 0 ? (
        <p className="mt-3 text-sm text-muted">No evidence items were produced.</p>
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
