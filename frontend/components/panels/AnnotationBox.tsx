"use client";

import { useCallback, useEffect, useState } from "react";
import type { Annotation, AnnotationList } from "@/lib/types";
import { getAnnotations, postAnnotation } from "@/lib/api";
import { Card, EmptyState, ErrorNote, Note, btnPrimary, errMessage, inputCls } from "./shared";

type Verdict = Annotation["verdict"];

const VERDICTS: { value: Verdict; label: string; hint: string; bar: string; sel: string }[] = [
  { value: "real", label: "Real", hint: "I think this is a genuine astronomical change", bar: "#2f6430", sel: "border-good bg-panel font-semibold text-good outline outline-1 outline-good" },
  { value: "artifact", label: "Artifact", hint: "I think this is an instrument or processing artifact", bar: "#b42d1c", sel: "border-bad bg-panel font-semibold text-bad outline outline-1 outline-bad" },
  { value: "known", label: "Known object", hint: "I recognise this as a catalogued object", bar: "#1f3f8a", sel: "border-accent bg-panel font-semibold text-accent outline outline-1 outline-accent" },
  { value: "unsure", label: "Unsure", hint: "I cannot tell", bar: "#4f565b", sel: "border-fg bg-panel font-semibold text-fg outline outline-1 outline-fg" },
];

export default function AnnotationBox({ candidateId }: { candidateId: string }) {
  const demo = candidateId.startsWith("demo_");
  const [data, setData] = useState<AnnotationList | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "ok" | "offline">(demo ? "offline" : "loading");
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [note, setNote] = useState("");
  const [author, setAuthor] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const load = useCallback(async () => {
    setLoadState("loading");
    try {
      const r = await getAnnotations(candidateId);
      setData(r);
      setLoadState("ok");
    } catch {
      setLoadState("offline");
    }
  }, [candidateId]);

  useEffect(() => {
    if (demo) return;
    let cancelled = false;
    getAnnotations(candidateId)
      .then((r) => {
        if (cancelled) return;
        setData(r);
        setLoadState("ok");
      })
      .catch(() => {
        if (!cancelled) setLoadState("offline");
      });
    return () => {
      cancelled = true;
    };
  }, [candidateId, demo]);

  const submit = async () => {
    if (!verdict) return;
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      const body: { verdict: Verdict; note: string; author?: string } = { verdict, note: note.trim() };
      if (author.trim()) body.author = author.trim();
      const r = await postAnnotation(candidateId, body);
      if (r && Array.isArray((r as AnnotationList).annotations)) setData(r as AnnotationList);
      else await load();
      setNote("");
      setVerdict(null);
      setDone(true);
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const tally = data?.tally ?? { real: 0, artifact: 0, known: 0, unsure: 0 };
  const total = tally.real + tally.artifact + tally.known + tally.unsure;
  const disabled = demo || loadState === "offline";
  const recent = [...(data?.annotations ?? [])].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)).slice(0, 8);

  return (
    <Card title="Human verification" subtitle="Your judgement helps triage candidates. Verdicts are shared and are not part of the automatic score.">
      {disabled && (
        <div className="mb-3">
          <EmptyState title={demo ? "Annotations need the live API" : "Annotations are offline"}>
            {demo
              ? "This is a precomputed demo snapshot. Verdicts and notes can only be saved when the investigation is run against the live ASTRA service."
              : "The annotation service could not be reached, so verdicts cannot be read or saved right now."}
            {!demo && (
              <p className="mt-2">
                <button type="button" className="text-accent underline underline-offset-2 hover:text-pencil" onClick={() => void load()}>
                  Try again
                </button>
              </p>
            )}
          </EmptyState>
        </div>
      )}

      <div role="radiogroup" aria-label="Your verdict" className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {VERDICTS.map((v) => (
          <button
            key={v.value}
            type="button"
            role="radio"
            aria-checked={verdict === v.value}
            title={v.hint}
            disabled={disabled}
            onClick={() => setVerdict(v.value)}
            className={`border px-2 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pencil disabled:cursor-not-allowed disabled:opacity-50 ${
              verdict === v.value ? v.sel : "border-line bg-panel text-fg hover:border-fg"
            }`}
          >
            {v.label}
          </button>
        ))}
      </div>

      <label className="mt-3 block text-sm text-muted">
        Note (optional)
        <textarea
          value={note}
          maxLength={500}
          rows={3}
          disabled={disabled}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What did you notice? Plain text only."
          className={`${inputCls} mt-1 resize-y disabled:opacity-50`}
        />
        <span className="mt-0.5 block text-right tabular-nums">{note.length}/500</span>
      </label>
      <label className="mt-1 block text-sm text-muted">
        Name or handle (optional)
        <input
          type="text"
          value={author}
          maxLength={40}
          disabled={disabled}
          onChange={(e) => setAuthor(e.target.value)}
          className={`${inputCls} mt-1 disabled:opacity-50`}
        />
        <span className="mt-0.5 block text-right tabular-nums">{author.length}/40</span>
      </label>

      <div className="mt-2 flex flex-wrap items-center gap-3">
        <button type="button" className={btnPrimary} disabled={disabled || !verdict || busy} onClick={submit}>
          {busy ? "Saving…" : "Submit verdict"}
        </button>
        {!disabled && !verdict && <span className="text-sm text-muted">Choose a verdict to enable submitting.</span>}
        {done && <span role="status" className="text-sm text-good">Thank you, your verdict was saved.</span>}
      </div>
      {error && (
        <div className="mt-2">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}

      {loadState === "loading" && <p className="mt-3 text-sm text-muted">Loading verdicts…</p>}
      {loadState === "ok" && (
        <div className="mt-4">
          <h4 className="serif mb-1.5 text-base font-semibold text-fg">Community tally</h4>
          {total === 0 ? (
            <p className="text-sm text-muted">No verdicts yet. Be the first.</p>
          ) : (
            <>
              <div
                className="flex h-3 w-full overflow-hidden border border-line bg-panel2"
                role="img"
                aria-label={VERDICTS.map((v) => `${v.label} ${tally[v.value]}`).join(", ")}
              >
                {VERDICTS.map((v) =>
                  tally[v.value] > 0 ? <div key={v.value} style={{ width: `${(tally[v.value] / total) * 100}%`, background: v.bar }} /> : null,
                )}
              </div>
              <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-sm text-muted">
                {VERDICTS.map((v) => (
                  <li key={v.value} className="inline-flex items-center gap-1">
                    <span aria-hidden className="inline-block h-3 w-3" style={{ background: v.bar }} />
                    {v.label} <span className="tabular-nums text-fg">{tally[v.value]}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {recent.some((a) => a.note) && (
            <ul className="mt-3 divide-y divide-line border-t border-line">
              {recent
                .filter((a) => a.note)
                .map((a) => (
                  <li key={a.id} className="py-2 text-sm">
                    <span className="font-medium text-fg">{VERDICTS.find((v) => v.value === a.verdict)?.label ?? a.verdict}</span>
                    <span className="text-muted">
                      {" "}
                      · {a.author || "anonymous"} · {a.created_at.slice(0, 10)}
                    </span>
                    <p className="mt-0.5 whitespace-pre-wrap break-words text-fg">{a.note}</p>
                  </li>
                ))}
            </ul>
          )}
          <div className="mt-2">
            <Note>Notes are shown as plain text and are not verified by ASTRA.</Note>
          </div>
        </div>
      )}
    </Card>
  );
}
