"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { Detector, Investigation } from "@/lib/types";
import { isoDateOnly } from "@/lib/format";
import { investigateHref, parseInvestigateParams, type DiffMethod, type PlayerMode } from "@/lib/url";
import Banner from "@/components/layout/Banner";
import ProgressChecklist from "@/components/layout/ProgressChecklist";
import EpochPlayer from "@/components/viewer/EpochPlayer";
import { useInvestigation } from "@/components/viewer/useInvestigation";

function pickDetector(inv: Investigation): Detector {
  const dets = new Set<number>();
  for (const f of inv.frames) if (f.kind === "visit_stack" && typeof f.detector === "number") dets.add(f.detector);
  if (dets.has(6)) return 6;
  if (dets.size) return Math.max(...dets);
  return 6;
}

export default function EmbedClient() {
  const sp = useSearchParams();
  const params = useMemo(() => parseInvestigateParams(sp), [sp]);
  const hasCoords = params.ra !== undefined && params.dec !== undefined;
  const state = useInvestigation({
    ra: hasCoords ? params.ra : undefined,
    dec: hasCoords ? params.dec : undefined,
    fov: params.fov,
    name: params.name,
    dets: params.dets,
  });
  const { inv, phase, error, fallback, note, retry } = state;

  if (!hasCoords && !params.name) {
    return (
      <div className="p-4 text-sm text-muted">
        No target given. Add <span className="mono">?ra=…&amp;dec=…</span> or <span className="mono">?name=…</span> to this URL.
      </div>
    );
  }

  return (
    <div className="space-y-2 p-2 sm:p-3">
      {error && (
        <Banner
          tone="danger"
          title={error.title}
          action={
            <button type="button" className="btn btn-sm" onClick={retry}>
              Retry
            </button>
          }
        >
          {error.message}
        </Banner>
      )}
      {!inv && !error && <ProgressChecklist progress={{ stage: phase === "resolving" ? "resolve" : "discover", pct: 0, message: note }} status="starting" />}
      {inv && <EmbedBody inv={inv} fallbackReason={fallback?.reason ?? null} />}
    </div>
  );
}

function EmbedBody({ inv, fallbackReason }: { inv: Investigation; fallbackReason: string | null }) {
  const sp = useSearchParams();
  const p = useMemo(() => parseInvestigateParams(sp), [sp]);
  const [detector, setDetector] = useState<Detector>(p.det ?? pickDetector(inv));
  const [mode, setMode] = useState<PlayerMode>(p.mode);
  const [visit, setVisit] = useState<string | undefined>(p.visit);
  const [visitB, setVisitB] = useState<string | undefined>(p.vb);
  const [method, setMethod] = useState<DiffMethod>(p.method);
  const name = inv.target?.name ?? inv.request.name ?? "Custom position";
  const full = investigateHref({ ...p, ra: inv.request.ra, dec: inv.request.dec, fov: inv.request.fov_arcmin, name: p.name ?? inv.request.name ?? undefined, det: detector, mode, visit, vb: visitB, method }, "/investigate");

  return (
    <>
      {inv.generated_from === "mock" && <Banner tone="danger" title="Development placeholder: not real data" />}
      {inv.generated_from === "demo_bundle" && (
        <Banner tone="info" title={`Precomputed snapshot of real SPHEREx data (generated ${isoDateOnly(inv.provenance?.generated_at ?? inv.created_at)})`}>
          {fallbackReason ?? ""}
        </Banner>
      )}
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="serif text-lg font-semibold">{name}</h1>
        <a href={full} target="_blank" rel="noopener noreferrer" className="text-sm">
          Open in ASTRA ↗
        </a>
      </div>
      <EpochPlayer
        inv={inv}
        detector={detector}
        onDetectorChange={setDetector}
        mode={mode}
        onModeChange={setMode}
        visitId={visit}
        onVisitChange={setVisit}
        visitB={visitB}
        onVisitBChange={setVisitB}
        diffMethod={method}
        onDiffMethodChange={setMethod}
        compact
      />
      <p className="text-xs text-muted">ASTRA is an independent project, not affiliated with or endorsed by NASA.</p>
    </>
  );
}
