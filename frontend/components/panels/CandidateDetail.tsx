"use client";

import { useState } from "react";
import type { Candidate, Investigation } from "@/lib/types";
import { assetUrl } from "@/lib/api";
import { formatDec, formatRA } from "@/lib/format";
import AiInvestigator from "./AiInvestigator";
import AnnotationBox from "./AnnotationBox";
import { KIND_LABEL } from "./CandidateList";
import { MatchTable, SERVICES } from "./CrossmatchPanel";
import EvidencePanel from "./EvidencePanel";
import { Card, Note, SectionTitle, StatusChip, num } from "./shared";

function Thumb({ src, label }: { src: string; label: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <figure className="w-[104px] shrink-0">
      {failed ? (
        <div className="flex aspect-square w-full items-center justify-center border border-dashed border-line px-1 text-center text-xs text-muted">
          image unavailable
        </div>
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={`Cutout of the candidate in visit ${label}`}
          width={104}
          height={104}
          loading="lazy"
          onError={() => setFailed(true)}
          className="negative aspect-square w-full border border-line bg-panel2 object-cover"
          style={{ imageRendering: "pixelated" }}
        />
      )}
      <figcaption className="mt-0.5 text-center text-sm text-muted">{label}</figcaption>
    </figure>
  );
}

export default function CandidateDetail({ inv, candidate }: { inv: Investigation; candidate: Candidate }) {
  const c = candidate;
  const motion = c.motion;
  const speed = motion ? Math.hypot(motion.pm_ra, motion.pm_dec) : null;
  // Position angle east of north.
  const pa = motion ? ((Math.atan2(motion.pm_ra, motion.pm_dec) * 180) / Math.PI + 360) % 360 : null;
  const visitLabel = (id: string) => inv.visits.find((v) => v.id === id)?.date_label ?? id;

  return (
    <div className="space-y-3">
      <Card
        title={`Candidate ${c.id}`}
        subtitle={`${KIND_LABEL[c.kind]} · peak Z ${num(c.peak_z, 1)} · ${formatRA(c.ra)} ${formatDec(c.dec)}`}
      >
        <Note tone="amber">
          A candidate is a source that changed between visits. It needs review: it may be an artifact, a known object or a
          real change, and nothing here is a confirmed finding.
        </Note>

        <SectionTitle>Cutouts</SectionTitle>
        {c.thumbnails.length === 0 ? (
          <p className="text-sm text-muted">No thumbnails were generated for this candidate.</p>
        ) : (
          <div className="flex gap-2 overflow-x-auto pb-1">
            {c.thumbnails.map((t) => (
              <Thumb key={t.visit_id} src={assetUrl(inv, t.url)} label={`${t.visit_id} · ${visitLabel(t.visit_id)}`} />
            ))}
          </div>
        )}

        {c.kind === "dipole" && (
          <>
            <SectionTitle>Motion estimate</SectionTitle>
            {motion ? (
              <p className="text-sm leading-relaxed text-fg">
                µα* ≈ {num(motion.pm_ra, 0)} mas/yr, µδ ≈ {num(motion.pm_dec, 0)} mas/yr (≈ {num(speed, 0)} mas/yr toward
                position angle {num(pa, 0)}° east of north).{" "}
                <span className="text-warn">Rough, from dipole separation</span>: the pair of positive and negative
                residuals is assumed to be one source that moved, which has not been verified.
              </p>
            ) : (
              <p className="text-sm text-muted">No motion estimate could be derived for this dipole.</p>
            )}
          </>
        )}

        <SectionTitle hint="Detections are grouped across detectors and visit pairs; recurrence is what separates candidates from noise.">
          Where it was seen
        </SectionTitle>
        <p className="text-sm text-fg">
          Detectors {c.detectors.map((d) => `D${d}`).join(", ") || "—"}; visit pairs{" "}
          {c.visit_pairs.map(([a, b]) => `${a}→${b}`).join(", ") || "—"}.
        </p>
      </Card>

      <EvidencePanel evidence={c.evidence} title="Evidence for this candidate" />

      <Card title="Catalog associations" subtitle="Nearby catalogued objects; associations only, not proof of identity">
        <div className="divide-y divide-line [&>div]:py-3 first:[&>div]:pt-0">
          {SERVICES.map((s) => {
            const r = c.crossmatch?.[s.key];
            return (
              <div key={s.key}>
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <h4 className="serif text-base font-semibold text-fg">{s.label}</h4>
                  <StatusChip status={r?.status ?? "unavailable"} message={r?.message} />
                </div>
                {r?.status === "ok" ? (
                  <MatchTable matches={r.matches} service={s.key} />
                ) : (
                  <p className="text-sm text-warn">{r?.message ?? "Unavailable: this check is missing."}</p>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      <AnnotationBox key={`${inv.id}:${c.id}`} candidateId={`${inv.id}:${c.id}`} />
      <AiInvestigator key={`${inv.id}:${c.id}`} inv={inv} subject="candidate" candidateId={c.id} />
    </div>
  );
}
