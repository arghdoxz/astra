"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import type { Detector, Investigation } from "@/lib/types";
import { isLive, reportUrl } from "@/lib/api";
import { formatDec, formatRA, isoDateOnly } from "@/lib/format";
import { addRecent, loadRecent, type RecentInvestigation } from "@/lib/history";
import { TARGETS, targetHref } from "@/lib/targets";
import { investigateHref, parseInvestigateParams, type InvestigateParams, type TabId } from "@/lib/url";
import Badge, { classificationTone, confidenceTone } from "@/components/layout/Badge";
import Banner from "@/components/layout/Banner";
import ProgressChecklist from "@/components/layout/ProgressChecklist";
import Tabs, { type TabDef } from "@/components/layout/Tabs";
import SearchBar from "@/components/search/SearchBar";
import EpochPlayer from "@/components/viewer/EpochPlayer";
import ObservationTimeline from "@/components/viewer/ObservationTimeline";
import { useInvestigation } from "@/components/viewer/useInvestigation";
import SkyContext from "@/components/sky/SkyContext";
import MetadataPanel from "@/components/panels/MetadataPanel";
import EvidencePanel from "@/components/panels/EvidencePanel";
import MotionPanel from "@/components/panels/MotionPanel";
import LightCurvePlot from "@/components/plots/LightCurvePlot";
import PhotometryTable from "@/components/panels/PhotometryTable";
import SpectrumPlot from "@/components/plots/SpectrumPlot";
import CandidateList from "@/components/panels/CandidateList";
import CandidateDetail from "@/components/panels/CandidateDetail";
import CrossmatchPanel from "@/components/panels/CrossmatchPanel";
import AiInvestigator from "@/components/panels/AiInvestigator";
import ProvenancePanel from "@/components/panels/ProvenancePanel";
import MethodsPanel from "@/components/panels/MethodsPanel";
import AnnotationBox from "@/components/panels/AnnotationBox";

function pickDetector(inv: Investigation): Detector {
  const dets = new Set<number>();
  for (const f of inv.frames) if (f.kind === "visit_stack" && typeof f.detector === "number") dets.add(f.detector);
  if (dets.has(6)) return 6;
  if (dets.size) return Math.max(...dets);
  return 6;
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      window.prompt("Copy this text:", text);
    } catch {
      /* ignore */
    }
    return false;
  }
}

export default function InvestigateClient() {
  const sp = useSearchParams();
  const router = useRouter();
  const params = useMemo(() => parseInvestigateParams(sp), [sp]);
  const latest = useRef<InvestigateParams>(params);
  useEffect(() => {
    latest.current = params;
  }, [params]);

  const update = useCallback(
    (patch: Partial<InvestigateParams>) => {
      const next = { ...latest.current, ...patch };
      latest.current = next;
      router.replace(investigateHref(next), { scroll: false });
    },
    [router],
  );

  const hasCoords = params.ra !== undefined && params.dec !== undefined;
  const hasTarget = hasCoords || !!params.name;

  const state = useInvestigation(
    { ra: hasCoords ? params.ra : undefined, dec: hasCoords ? params.dec : undefined, fov: params.fov, name: params.name, dets: params.dets },
    (ra, dec, name) => update({ ra, dec, name }),
  );

  if (!hasTarget) return <StartScreen />;

  const { inv, phase, error, fallback, note, retry } = state;

  return (
    <div className="page space-y-4 py-5">
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
          {error.message}{" "}
          <span className="text-muted">
            Try a library target: {TARGETS.map((t, i) => (
              <span key={t.slug}>
                {i > 0 && ", "}
                <Link href={targetHref(t)}>{t.name}</Link>
              </span>
            ))}
            .
          </span>
        </Banner>
      )}

      {!inv && !error && (
        <ProgressChecklist progress={{ stage: phase === "resolving" ? "resolve" : "discover", pct: 0, message: note }} status="starting" />
      )}

      {inv && (
        <Workspace
          key={inv.id}
          inv={inv}
          fallbackReason={fallback?.reason ?? null}
          params={params}
          update={update}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ start screen */

function StartScreen() {
  const [recent, setRecent] = useState<RecentInvestigation[]>([]);
  useEffect(() => {
    const t = window.setTimeout(() => setRecent(loadRecent()), 0); // localStorage is client-only; read after hydration
    return () => window.clearTimeout(t);
  }, []);
  return (
    <div className="page space-y-10 py-8">
      <div className="max-w-3xl space-y-3">
        <h1 className="serif text-3xl font-semibold">Investigate a position on the sky</h1>
        <p className="max-w-[62ch] text-fg">
          Enter a name or coordinates. ASTRA finds every SPHEREx exposure of that spot, stacks them into visits, and shows how the sky changed, with the measurements and evidence behind it.
        </p>
        <div className="card card-pad">
          <SearchBar />
        </div>
      </div>
      {recent.length > 0 && (
        <section aria-label="Recent investigations">
          <h2 className="h-sec mb-2">Recent in this browser</h2>
          <ul className="max-w-3xl border-t border-fg">
            {recent.slice(0, 6).map((r) => (
              <li key={r.href} className="border-b border-line">
                <Link href={r.href} className="flex flex-wrap items-baseline justify-between gap-x-4 px-1 py-2 text-fg no-underline hover:bg-panel hover:text-fg hover:no-underline">
                  <span className="serif text-lg">{r.name ?? "Custom position"}</span>
                  <span className="mono text-sm text-muted">
                    {r.ra.toFixed(4)}, {r.dec.toFixed(4)} · {r.fov_arcmin}′
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ workspace */

function Workspace({
  inv,
  fallbackReason,
  params,
  update,
}: {
  inv: Investigation;
  fallbackReason: string | null;
  params: InvestigateParams;
  update: (patch: Partial<InvestigateParams>) => void;
}) {
  const [chan, setChan] = useState<{ obsIds: string[]; wl: number } | null>(null);
  const [frame, setFrame] = useState<{ mjd: number; visitId?: string } | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [aiSubject, setAiSubject] = useState<"target" | "candidate">("target");

  const autoDet = useMemo(() => pickDetector(inv), [inv]);
  const det: Detector = params.det ?? autoDet;
  const cand = inv.candidates.find((c) => c.id === params.cand) ?? null;
  const tab: TabId = params.tab ?? (cand ? "candidates" : "evidence");
  const ev = inv.evidence;
  const done = inv.status === "done";
  const running = inv.status === "queued" || inv.status === "running";

  // remember this investigation for the "recent" list
  useEffect(() => {
    if (!done) return;
    addRecent({
      id: inv.id,
      name: inv.target?.name ?? inv.request.name ?? undefined,
      ra: inv.request.ra,
      dec: inv.request.dec,
      fov_arcmin: inv.request.fov_arcmin,
      href: window.location.pathname + window.location.search,
    });
  }, [done, inv.id, inv.request.ra, inv.request.dec, inv.request.fov_arcmin, inv.request.name, inv.target?.name]);

  const onFrameChange = useCallback((f: { mjd: number; visitId?: string }) => setFrame((p) => (p && p.mjd === f.mjd && p.visitId === f.visitId ? p : f)), []);

  const name = inv.target?.name ?? inv.request.name ?? "Custom position";
  const embedHref = investigateHref({ ...params, ra: inv.request.ra, dec: inv.request.dec, fov: inv.request.fov_arcmin, name: params.name ?? inv.request.name ?? undefined, cand: undefined, tab: undefined }, "/embed");

  async function share() {
    const ok = await copyText(window.location.href);
    setCopied(ok ? "Link copied" : "Copy the link from the prompt");
    setTimeout(() => setCopied(null), 2200);
  }
  async function copyEmbed() {
    const snippet = `<iframe src="${window.location.origin}${embedHref}" width="720" height="760" style="border:0" title="ASTRA viewer" loading="lazy"></iframe>`;
    const ok = await copyText(snippet);
    setCopied(ok ? "Embed code copied" : "Copy the code from the prompt");
    setTimeout(() => setCopied(null), 2200);
  }

  const novelty = ev?.novelty === "catalogued" ? "Catalogued source" : ev?.novelty === "uncatalogued" ? "No catalogue match" : ev?.novelty === "unknown" ? "Novelty unknown" : null;

  const tabs: TabDef<TabId>[] = [
    { id: "evidence", label: "Evidence" },
    { id: "motion", label: "Motion" },
    { id: "brightness", label: "Brightness" },
    { id: "spectrum", label: "Spectrum" },
    { id: "candidates", label: "Candidates", badge: inv.candidates.length ? <span className="chip chip-amber">{inv.candidates.length}</span> : undefined },
    { id: "catalogs", label: "Catalogs" },
    { id: "ai", label: "AI Investigator" },
    { id: "provenance", label: "Provenance" },
  ];

  return (
    <>
      {/* data-source banner */}
      {inv.generated_from === "mock" && (
        <Banner tone="danger" title="Development placeholder: not real data">
          This page is showing a mock bundle used only for UI development. Nothing here was measured from SPHEREx.
          {fallbackReason ? ` (${fallbackReason})` : ""}
        </Banner>
      )}
      {inv.generated_from === "demo_bundle" && (
        <Banner tone="info" title={`Precomputed snapshot of real SPHEREx data (generated ${isoDateOnly(inv.provenance?.generated_at ?? inv.created_at)})`}>
          {fallbackReason ? `${fallbackReason} ` : ""}This is a saved result, not a live run. Live investigation, AI explanations and annotations need the backend.
        </Banner>
      )}

      {/* header strip */}
      <header className="card card-pad">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="serif text-3xl font-semibold sm:text-4xl">{name}</h1>
            <p className="mono mt-1 border-t border-line pt-1 text-sm text-fg">
              RA {formatRA(inv.request.ra)} · Dec {formatDec(inv.request.dec)}{" "}
              <span className="text-muted">
                ({inv.request.ra.toFixed(5)}, {inv.request.dec.toFixed(5)}) · FOV {inv.request.fov_arcmin}′
              </span>
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {!running && ev?.classification_label && <Badge tone={classificationTone(ev.classification)}>{ev.classification_label}</Badge>}
              {!running && ev?.confidence && (
                <Badge tone={confidenceTone(ev.confidence)} title={ev.confidence_reason}>
                  Confidence: {ev.confidence}
                </Badge>
              )}
              {!running && novelty && <Badge>{novelty}</Badge>}
              {inv.target?.otype && <Badge title="SIMBAD object type">{inv.target.otype}</Badge>}
              {running && <span className="mono text-sm text-muted">Running…</span>}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="btn btn-sm" onClick={share}>
              Share link
            </button>
            <a className="btn btn-sm no-underline hover:no-underline" href={embedHref} target="_blank" rel="noopener noreferrer">
              Embed view
            </a>
            <button type="button" className="btn btn-sm" onClick={copyEmbed}>
              Copy iframe code
            </button>
            {isLive(inv) && done && (
              <span className="flex items-center gap-1 text-sm text-muted">
                Report:
                {(["json", "csv", "md"] as const).map((f) => (
                  <a key={f} className="btn btn-sm no-underline hover:no-underline" href={reportUrl(inv.id, f)} target="_blank" rel="noopener noreferrer">
                    {f.toUpperCase()}
                  </a>
                ))}
              </span>
            )}
            <span role="status" className="text-sm text-good">
              {copied}
            </span>
          </div>
        </div>
      </header>

      {inv.warnings.length > 0 && (
        <Banner tone="warn" title={inv.warnings.length === 1 ? "Caveat" : `${inv.warnings.length} caveats`}>
          <ul className="list-disc pl-5">
            {inv.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </Banner>
      )}

      {running && <ProgressChecklist progress={inv.progress} status={inv.status} />}

      {/* player + context */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="min-w-0 space-y-2">
          {chan && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="chip chip-cyan">
                Showing exposures at λ≈{chan.wl.toFixed(2)} µm ({chan.obsIds.length} exposure{chan.obsIds.length === 1 ? "" : "s"})
                <button type="button" aria-label="Clear wavelength filter" className="ml-1 cursor-pointer text-fg hover:text-accent" onClick={() => setChan(null)}>
                  ✕
                </button>
              </span>
            </div>
          )}
          <EpochPlayer
            inv={inv}
            detector={det}
            onDetectorChange={(d) => update({ det: d })}
            mode={params.mode}
            onModeChange={(m) => update({ mode: m })}
            visitId={params.visit}
            onVisitChange={(id) => update({ visit: id })}
            visitB={params.vb}
            onVisitBChange={(id) => update({ vb: id })}
            exposureFilter={chan?.obsIds ?? null}
            selectedCandidate={cand}
            diffMethod={params.method}
            onDiffMethodChange={(m) => update({ method: m })}
            onFrameChange={onFrameChange}
          />
        </div>
        <div className="min-w-0 space-y-4">
          <SkyContext inv={inv} selectedVisit={frame?.visitId ?? params.visit ?? null} />
          <MetadataPanel inv={inv} selectedVisit={frame?.visitId ?? params.visit ?? null} detector={det} />
        </div>
      </div>

      <ObservationTimeline
        inv={inv}
        selectedVisit={params.visit ?? frame?.visitId ?? null}
        currentMjd={frame?.mjd ?? null}
        onSelectVisit={(id) => update({ visit: id, mode: params.mode === "exposures" || params.mode === "diff" ? "visits" : params.mode })}
      />

      {/* analysis tabs */}
      <section aria-label="Analysis">
        <Tabs tabs={tabs} value={tab} onChange={(t) => update({ tab: t })}>
          {tab === "evidence" && (
            <div className="space-y-4">
              {ev?.items ? <EvidencePanel evidence={ev} /> : <p className="text-sm text-muted">Evidence appears when scoring finishes.</p>}
              {isLive(inv) && done && (
                <div className="border-t border-line pt-3">
                  <h3 className="serif mb-1 text-lg font-semibold">Your verdict on this target</h3>
                  <AnnotationBox candidateId={`${inv.id}:target`} />
                </div>
              )}
            </div>
          )}
          {tab === "motion" && <MotionPanel inv={inv} />}
          {tab === "brightness" && (
            <div className="space-y-6">
              <LightCurvePlot inv={inv} />
              <PhotometryTable inv={inv} />
            </div>
          )}
          {tab === "spectrum" && (
            <div className="space-y-3">
              <SpectrumPlot
                inv={inv}
                onSelectChannel={(obsIds, wl) => {
                  setChan({ obsIds, wl });
                  update({ mode: "exposures" });
                  if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
                }}
              />
              <p className="text-sm text-muted">Click a spectral channel to show only the exposures that sampled it in the image player.</p>
            </div>
          )}
          {tab === "candidates" && (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
              <CandidateList inv={inv} selectedId={cand?.id ?? null} onSelect={(id) => update({ cand: id, tab: "candidates" })} />
              <div className="min-w-0">
                {cand ? (
                  <CandidateDetail inv={inv} candidate={cand} />
                ) : (
                  <p className="text-sm text-muted">Select a candidate to see its evidence, thumbnails and catalogue matches.</p>
                )}
              </div>
            </div>
          )}
          {tab === "catalogs" && <CrossmatchPanel inv={inv} />}
          {tab === "ai" && (
            <div className="space-y-3">
              {cand && (
                <div role="group" aria-label="Explanation subject" className="flex gap-1">
                  <button type="button" className="btn btn-sm" aria-pressed={aiSubject === "target"} onClick={() => setAiSubject("target")}>
                    The target
                  </button>
                  <button type="button" className="btn btn-sm" aria-pressed={aiSubject === "candidate"} onClick={() => setAiSubject("candidate")}>
                    Candidate {cand.id}
                  </button>
                </div>
              )}
              {cand && aiSubject === "candidate" ? (
                <AiInvestigator key={`c-${cand.id}`} inv={inv} subject="candidate" candidateId={cand.id} />
              ) : (
                <AiInvestigator key="t" inv={inv} subject="target" />
              )}
            </div>
          )}
          {tab === "provenance" && (
            <div className="space-y-6">
              <ProvenancePanel inv={inv} />
              <MethodsPanel inv={inv} />
            </div>
          )}
        </Tabs>
      </section>
    </>
  );
}
