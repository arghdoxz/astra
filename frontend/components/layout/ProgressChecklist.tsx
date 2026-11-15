import type { Investigation, Stage } from "@/lib/types";

const STAGES: { id: Stage; label: string }[] = [
  { id: "resolve", label: "Resolve target" },
  { id: "discover", label: "Find SPHEREx exposures" },
  { id: "fetch", label: "Fetch cutouts" },
  { id: "stack", label: "Build visit stacks & difference images" },
  { id: "measure", label: "Measure position & brightness" },
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
        <h2 className="h-sec">{status === "starting" ? "Starting investigation…" : "Investigation in progress"}</h2>
        <span className="mono text-sm text-muted">{pct}%</span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded bg-panel2" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full rounded bg-accent transition-[width] duration-300" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 text-sm text-muted min-h-[1.4em]">{progress.message}</p>
      <ol className="mt-3 grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
        {STAGES.map((s, i) => {
          const done = i < activeIdx;
          const active = i === activeIdx;
          return (
            <li key={s.id} className="flex items-center gap-2 text-sm">
              <span
                aria-hidden
                className={`inline-flex h-4 w-4 items-center justify-center rounded-full border text-[10px] ${
                  done
                    ? "border-good bg-good/15 text-good"
                    : active
                      ? "border-accent text-accent"
                      : "border-line text-transparent"
                }`}
              >
                {done ? "✓" : active ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> : "·"}
              </span>
              <span className={done ? "text-fg" : active ? "text-accent" : "text-muted"}>{s.label}</span>
              <span className="sr-only">{done ? "(done)" : active ? "(in progress)" : "(waiting)"}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
