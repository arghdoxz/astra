"use client";

import { useState } from "react";
import type { Explanation, Investigation, SectionKey } from "@/lib/types";
import { explain, isLive } from "@/lib/api";
import { Card, EmptyState, ErrorNote, KIND_ORDER, KindTag, Pill, btnPrimary, errMessage, inputCls, kindDescription } from "./shared";

const SECTION_ORDER: SectionKey[] = [
  "summary",
  "movement",
  "brightness",
  "spectrum",
  "catalog_matches",
  "uncertainties",
  "alternative_explanations",
  "next_steps",
];

export default function AiInvestigator({
  inv,
  subject,
  candidateId,
}: {
  inv: Investigation;
  subject: "target" | "candidate";
  candidateId?: string;
}) {
  const live = isLive(inv);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Explanation | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const req: { subject: "target" | "candidate"; candidate_id?: string; question?: string } = { subject };
      if (subject === "candidate" && candidateId) req.candidate_id = candidateId;
      if (question.trim()) req.question = question.trim();
      setResult(await explain(inv.id, req));
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  };

  // The 8 sections always arrive in contract order; sort defensively.
  const sections = result
    ? [...result.sections].sort((a, b) => SECTION_ORDER.indexOf(a.key) - SECTION_ORDER.indexOf(b.key))
    : [];

  return (
    <Card
      title="Explain this evidence"
      subtitle={subject === "candidate" ? `Plain-language reading of candidate ${candidateId ?? ""}` : "Plain-language reading of the evidence for the target"}
    >
      {!live && (
        <div className="mb-3">
          <EmptyState title="Explanations need the live API">
            This is a precomputed snapshot with no connection to the explanation service. The deterministic evidence summary
            and per-item reasons above are always available without AI.
          </EmptyState>
        </div>
      )}

      <label className="block text-xs text-[#8a97b4]">
        Optional question
        <input
          type="text"
          value={question}
          maxLength={300}
          disabled={!live || busy}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && live && !busy) void run();
          }}
          placeholder="e.g. Why is this flagged as an artifact?"
          className={`${inputCls} mt-1 disabled:opacity-50`}
        />
        <span className="mt-0.5 block text-right tabular-nums">{question.length}/300</span>
      </label>

      <div className="mt-1 flex flex-wrap items-center gap-3">
        <button type="button" className={btnPrimary} onClick={run} disabled={!live || busy}>
          {busy ? "Explaining…" : result ? "Explain again" : "Explain this evidence"}
        </button>
        {busy && (
          <span role="status" className="text-xs text-[#8a97b4]">
            Reading the evidence… this can take up to a minute.
          </span>
        )}
      </div>
      {error && (
        <div className="mt-2">
          <ErrorNote>
            {error} The deterministic evidence summary above is unaffected.
          </ErrorNote>
        </div>
      )}

      {result && (
        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Pill
              className={result.source === "gemini" ? "border-[#8fa8ff]/50 bg-[#8fa8ff]/10 text-[#a9bbff]" : "border-[#1d2742] text-[#c3cde3]"}
              title={result.source === "gemini" ? "Wording written by an AI model from the evidence JSON" : "Wording produced by fixed rules, no AI involved"}
            >
              {result.source === "gemini" ? `AI: ${result.model ?? "Gemini"}` : "Deterministic template"}
            </Pill>
            <Pill
              className={result.grounding.passed ? "border-[#59d98e]/40 bg-[#59d98e]/10 text-[#59d98e]" : "border-[#f2b84b]/40 bg-[#f2b84b]/10 text-[#f2b84b]"}
              title="Every number in the text must also appear in the measured evidence"
            >
              {result.grounding.passed ? "Grounding check: passed ✓" : "Grounding check: failed — template used"}
            </Pill>
          </div>

          <p
            role="note"
            className="rounded-md border border-[#f2b84b]/40 bg-[#f2b84b]/10 px-3 py-2 text-xs font-medium leading-relaxed text-[#f2d9a0]"
          >
            {result.disclaimer}
          </p>

          <div className="space-y-3">
            {sections.map((s) => (
              <section key={s.key} aria-labelledby={`ai-${inv.id}-${s.key}`}>
                <h4 id={`ai-${inv.id}-${s.key}`} className="mb-1 text-sm font-semibold text-[#e6ebf5]">
                  {s.title}
                </h4>
                {s.statements.length === 0 ? (
                  <p className="text-xs text-[#8a97b4]">Nothing to report.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {s.statements.map((st, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm leading-relaxed text-[#c3cde3]">
                        <span className="mt-0.5">
                          <KindTag kind={st.kind} />
                        </span>
                        <span className="min-w-0 break-words">{st.text}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            ))}
          </div>

          <div className="rounded-md border border-[#1d2742] bg-[#0a0f1c]/60 px-3 py-2">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-[#8a97b4]">Legend</p>
            <ul className="space-y-1">
              {KIND_ORDER.map((k) => (
                <li key={k} className="flex items-start gap-2 text-xs text-[#8a97b4]">
                  <KindTag kind={k} />
                  <span>{kindDescription(k)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Card>
  );
}
