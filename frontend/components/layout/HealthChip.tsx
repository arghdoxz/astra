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

  let tone = "text-muted";
  let label = "Connecting to the archive server…";
  let title = "Checking the ASTRA backend (a sleeping free-tier server can take up to a minute to wake).";
  if (state.kind === "checking" && state.attempt > 0) label = "Waking the archive server…";
  if (state.kind === "ok") {
    tone = "text-good";
    label = "Live server: online";
    title = Object.entries(state.health.services ?? {}).map(([k, v]) => `${k}: ${v}`).join("\n") || "API online";
  } else if (state.kind === "degraded") {
    tone = "text-warn";
    const bad = Object.entries(state.health.services ?? {})
      .filter(([, v]) => v === "down" || v === "degraded")
      .map(([k]) => k);
    label = `Live server: online, ${bad.join(", ") || "some services"} not answering`;
    title = Object.entries(state.health.services ?? {}).map(([k, v]) => `${k}: ${v}`).join("\n");
  } else if (state.kind === "offline") {
    tone = "text-warn";
    label = "Live server offline. Saved demo plates still work. Retry";
    title = "The live backend could not be reached. Click to retry. Precomputed demo snapshots still work for library targets that have one.";
  }

  return (
    <button
      type="button"
      onClick={retry}
      title={title}
      aria-live="polite"
      disabled={state.kind !== "offline"}
      className={`max-w-full self-start text-left text-sm disabled:cursor-default ${tone} ${state.kind === "offline" ? "cursor-pointer underline" : ""}`}
    >
      {label}
    </button>
  );
}
