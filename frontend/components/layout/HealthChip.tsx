"use client";

import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";
import type { Health } from "@/lib/types";

type State =
  | { kind: "checking"; attempt: number }
  | { kind: "ok"; health: Health }
  | { kind: "degraded"; health: Health }
  | { kind: "offline" };

export default function HealthChip() {
  const [state, setState] = useState<State>({ kind: "checking", attempt: 0 });
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const attempt = (n: number) => {
      getHealth()
        .then((health) => {
          if (cancelled) return;
          const bad = Object.values(health.services ?? {}).some((v) => v === "down" || v === "degraded");
          setState({ kind: bad ? "degraded" : "ok", health });
        })
        .catch(() => {
          if (cancelled) return;
          // Free-tier backends cold-start: retry a few times before declaring offline.
          if (n < 3) {
            setState({ kind: "checking", attempt: n + 1 });
            timer = setTimeout(() => attempt(n + 1), 6000);
          } else {
            setState({ kind: "offline" });
          }
        });
    };
    attempt(0);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [retryKey]);

  function retry() {
    if (state.kind !== "offline") return;
    setState({ kind: "checking", attempt: 0 });
    setRetryKey((k) => k + 1);
  }

  let dot = "bg-muted";
  let label = "Connecting to API…";
  let title = "Checking the ASTRA backend (a sleeping free-tier server can take up to a minute to wake).";
  if (state.kind === "checking" && state.attempt > 0) label = "Waking API…";
  if (state.kind === "ok") {
    dot = "bg-good";
    label = "API online";
    title = Object.entries(state.health.services ?? {}).map(([k, v]) => `${k}: ${v}`).join("\n") || "API online";
  } else if (state.kind === "degraded") {
    dot = "bg-warn";
    label = "API degraded";
    title = Object.entries(state.health.services ?? {}).map(([k, v]) => `${k}: ${v}`).join("\n");
  } else if (state.kind === "offline") {
    dot = "bg-warn";
    label = "API offline — demo snapshots available";
    title = "The live backend could not be reached. Click to retry. Precomputed demo snapshots still work for library targets that have one.";
  }

  return (
    <button
      type="button"
      onClick={retry}
      title={title}
      aria-live="polite"
      className="inline-flex max-w-full items-center gap-2 rounded-sm border border-line bg-panel mono px-3 py-1 text-xs text-muted transition-colors hover:text-fg cursor-pointer"
    >
      <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${dot} ${state.kind === "checking" ? "animate-pulse" : ""}`} />
      <span className="truncate">{label}</span>
    </button>
  );
}
