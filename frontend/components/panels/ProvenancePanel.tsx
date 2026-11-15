"use client";

import type { Investigation } from "@/lib/types";
import { isLive, reportUrl } from "@/lib/api";
import { Card, Note, SectionTitle, StatusChip, TableWrap, btn, mjdToDate, tdCls, thCls } from "./shared";

const ORIGIN: Record<Investigation["generated_from"], { label: string; tone: "cyan" | "amber"; text: string }> = {
  live: {
    label: "Live computation",
    tone: "cyan",
    text: "Computed just now from SPHEREx data retrieved from IRSA.",
  },
  demo_bundle: {
    label: "Precomputed snapshot of real data",
    tone: "cyan",
    text: "Real SPHEREx observations processed ahead of time with the same pipeline and saved as a static bundle.",
  },
  mock: {
    label: "MOCK placeholder",
    tone: "amber",
    text: "Development placeholder data. These are NOT real SPHEREx observations and must not be interpreted scientifically.",
  },
};

const CREDITS =
  "SPHEREx data: NASA/IPAC Infrared Science Archive (IRSA), SPHEREx DR1 and Quick Release 3. Catalogs: Gaia DR3 (ESA/Gaia/DPAC), SIMBAD and Sesame (CDS, Strasbourg), CatWISE2020, SkyBoT (IMCCE). Background sky imagery: HiPS surveys via CDS Aladin Lite. ASTRA is an independent educational tool, not a NASA product.";

export default function ProvenancePanel({ inv }: { inv: Investigation }) {
  const p = inv.provenance;
  const live = isLive(inv);
  const origin = ORIGIN[inv.generated_from] ?? ORIGIN.mock;

  const downloadBundle = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(inv, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `astra_${inv.id}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <Card title="Provenance" subtitle="Where these numbers came from">
      <Note tone={origin.tone}>
        <strong>{origin.label}.</strong> {origin.text}
      </Note>

      <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-1.5 text-xs sm:grid-cols-2">
        <Row k="Collections" v={p.collections.length ? p.collections.join(", ") : "—"} />
        <Row k="Pipeline versions" v={p.pipeline_versions.length ? p.pipeline_versions.join(", ") : "not reported"} />
        <Row
          k="Exposures"
          v={`${p.n_exposures_used} used of ${p.n_exposures_found} found`}
        />
        <Row
          k="Sampling"
          v={p.sampling === "all" ? "all exposures" : "evenly sampled per visit and detector (cap reached)"}
        />
        <Row k="Generated" v={p.generated_at ? p.generated_at.replace("T", " ").slice(0, 19) + " UTC" : "—"} />
        <Row k="Software" v={p.software} />
      </dl>

      <SectionTitle>Service status</SectionTitle>
      {Object.keys(p.services ?? {}).length === 0 ? (
        <p className="text-xs text-[#8a97b4]">No service calls recorded.</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(p.services).map(([k, v]) => (
            <StatusChip key={k} label={k} status={v} />
          ))}
        </div>
      )}
      {inv.warnings.length > 0 && (
        <>
          <SectionTitle>Warnings</SectionTitle>
          <ul className="list-inside list-disc space-y-0.5 text-xs text-[#f2d9a0]">
            {inv.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </>
      )}

      <SectionTitle>Exposures used</SectionTitle>
      <details className="rounded-md border border-[#1d2742] bg-[#0a0f1c]/60 px-3 py-2">
        <summary className="cursor-pointer text-xs font-medium text-[#5ad1e6] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#5ad1e6]">
          Show {inv.exposures.length} exposure{inv.exposures.length === 1 ? "" : "s"}
        </summary>
        <div className="mt-2 max-h-72 overflow-y-auto">
          <TableWrap>
            <table className="w-full min-w-[520px] border-collapse">
              <thead className="sticky top-0 bg-[#0a0f1c]">
                <tr className="border-b border-[#1d2742]">
                  <th className={thCls}>obs_id</th>
                  <th className={thCls}>Publisher DID</th>
                  <th className={thCls}>D</th>
                  <th className={thCls}>Date</th>
                  <th className={thCls}>Status</th>
                </tr>
              </thead>
              <tbody>
                {inv.exposures.map((e) => (
                  <tr key={`${e.obs_id}-${e.detector}`} className="border-b border-[#1d2742]/60 last:border-0">
                    <td className={`${tdCls} font-mono`}>{e.obs_id}</td>
                    <td className={`${tdCls} font-mono`}>{e.did}</td>
                    <td className={tdCls}>{e.detector}</td>
                    <td className={tdCls}>{e.date_obs?.slice(0, 10) ?? mjdToDate(e.mjd)}</td>
                    <td className={tdCls}>
                      <span className={e.status === "ok" ? "text-[#59d98e]" : e.status === "failed" ? "text-[#f26b6b]" : "text-[#f2b84b]"}>{e.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </div>
      </details>

      <SectionTitle hint={live ? "Generated by the ASTRA service." : "This is a static snapshot; the service reports are unavailable, so the bundle is exported from your browser."}>
        Export
      </SectionTitle>
      <div className="flex flex-wrap gap-2">
        {live ? (
          <>
            <a className={btn} href={reportUrl(inv.id, "json")} download>
              JSON report
            </a>
            <a className={btn} href={reportUrl(inv.id, "csv")} download>
              CSV photometry
            </a>
            <a className={btn} href={reportUrl(inv.id, "md")} download>
              Markdown summary
            </a>
          </>
        ) : (
          <button type="button" className={btn} onClick={downloadBundle}>
            Download bundle (JSON)
          </button>
        )}
      </div>

      <p className="mt-4 border-t border-[#1d2742] pt-3 text-[11px] leading-relaxed text-[#8a97b4]">{CREDITS}</p>
    </Card>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-2 border-b border-[#1d2742]/50 pb-1">
      <dt className="text-[#8a97b4]">{k}</dt>
      <dd className="break-words text-right text-[#e6ebf5]">{v}</dd>
    </div>
  );
}
