import type { Investigation, Stage } from "@/lib/types";

const STAGES: { id: Stage; label: string }[] = [
  { id: "resolve", label: "Resolve target" },
  { id: "discover", label: "Find SPHEREx exposures" },
  { id: "fetch", label: "Fetch cutouts" },
  { id: "stack", label: "Build visit stacks and difference images" },
  { id: "measure", label: "Measure position and brightness" },
  { id: "crossmatch", label: "Cross-match catalogues" },
  { id: "score", label: "Score the evidence" },
  { id: "render", label: "Render frames" },
];

export default function ProgressChecklist({
  progress,
  status,
}: {
  progress: Investigation["progress"];
  status: Investigation["status"] | "starting";
}) {
  const activeIdx = progress.stage === "done" ? STAGES.length : STAGES.findIndex((s) => s.id === progress.stage);
  const pct = Math.max(0, Math.min(100, Math.round(progress.pct)));
  return (
    <section className="card card-pad fade-in" aria-label="Investigation progress" aria-live="polite">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="h-sec">{status === "starting" ? "Starting investigation" : "Reading the plates"}</h2>
        <span className="mono text-sm text-muted" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          {pct}% done
        </span>
      </div>
      <p className="mt-1 min-h-[1.4em] text-sm text-muted">{progress.message}</p>
      <ol className="mono mt-3 border-t border-line pt-3 text-sm leading-7">
        {STAGES.map((s, i) => {
          const done = i < activeIdx;
          const active = i === activeIdx;
          return (
            <li key={s.id} className={done ? "text-fg" : active ? "font-bold text-pencil" : "text-muted"}>
              <span aria-hidden className="inline-block w-8">{done ? "[x]" : active ? "[>]" : "[ ]"}</span>
              {s.label}
              <span className="sr-only">{done ? " (done)" : active ? " (in progress)" : " (waiting)"}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
