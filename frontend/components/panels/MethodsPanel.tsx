"use client";

import type { Investigation } from "@/lib/types";
import { Card, EmptyState } from "./shared";

export default function MethodsPanel({ inv }: { inv: Investigation }) {
  const methods = inv.methods ?? [];
  return (
    <Card title="Methods and limits" subtitle="What ASTRA actually does, including what is approximate or not implemented">
      {methods.length === 0 ? (
        <EmptyState title="No method notes recorded">The investigation did not include method descriptions.</EmptyState>
      ) : (
        <ul className="divide-y divide-line">
          {methods.map((m) => (
            <li key={m.key} className="flex items-start gap-2.5 py-2">
              <span
                className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center border text-sm font-bold ${
                  m.implemented
                    ? "border-good bg-panel text-good"
                    : "border-dashed border-muted bg-panel text-muted"
                }`}
              >
                <span aria-hidden>{m.implemented ? "✓" : "–"}</span>
                <span className="sr-only">{m.implemented ? "Implemented" : "Not implemented"}</span>
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-fg">
                  {m.label}
                  {!m.implemented && <span className="ml-2 text-sm font-normal text-muted">not implemented</span>}
                </p>
                <p className="mt-0.5 text-sm leading-relaxed text-muted">{m.description}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
