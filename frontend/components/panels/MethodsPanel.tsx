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
        <ul className="divide-y divide-[#1d2742]/70">
          {methods.map((m) => (
            <li key={m.key} className="flex items-start gap-2.5 py-2">
              <span
                className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${
                  m.implemented
                    ? "border-[#59d98e]/40 bg-[#59d98e]/10 text-[#59d98e]"
                    : "border-dashed border-[#8a97b4]/60 text-[#8a97b4]"
                }`}
              >
                <span aria-hidden>{m.implemented ? "✓" : "–"}</span>
                <span className="sr-only">{m.implemented ? "Implemented" : "Not implemented"}</span>
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-[#e6ebf5]">
                  {m.label}
                  {!m.implemented && <span className="ml-2 text-xs font-normal text-[#8a97b4]">not implemented</span>}
                </p>
                <p className="mt-0.5 text-xs leading-relaxed text-[#8a97b4]">{m.description}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
