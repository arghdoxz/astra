"use client";

import { useMemo, useState } from "react";
import type { CatalogMatch, CatalogResult, CrossMatch, Investigation } from "@/lib/types";
import { crossmatch, isLive } from "@/lib/api";
import { formatDec, formatRA } from "@/lib/format";
import { Card, EmptyState, ErrorNote, Note, SectionTitle, StatusChip, TableWrap, btnPrimary, errMessage, num, tdCls, thCls } from "./shared";

export const SERVICES: { key: keyof CrossMatch; label: string; blurb: string }[] = [
  { key: "gaia", label: "Gaia DR3", blurb: "optical astrometry, proper motion, parallax" },
  { key: "simbad", label: "SIMBAD", blurb: "object identifiers and types" },
  { key: "catwise", label: "CatWISE2020", blurb: "mid-infrared sources with proper motion" },
  { key: "skybot", label: "SkyBoT", blurb: "known solar-system bodies" },
];

/** Compact match table, reused by candidate details. */
export function MatchTable({ matches, service }: { matches: CatalogMatch[]; service: CatalogResult["service"] }) {
  if (matches.length === 0) return <p className="text-xs text-[#8a97b4]">No associations within the match radius.</p>;
  return (
    <TableWrap>
      <table className="w-full min-w-[520px] border-collapse">
        <thead>
          <tr className="border-b border-[#1d2742]">
            <th className={thCls}>Id</th>
            <th className={thCls}>Sep (″)</th>
            <th className={thCls}>Mag</th>
            <th className={thCls}>PM (mas/yr)</th>
            <th className={thCls}>ϖ (mas)</th>
            <th className={thCls}>Type / class</th>
            <th className={thCls} title="Catalog position was propagated to the SPHEREx epoch before matching">
              Epoch ✓
            </th>
          </tr>
        </thead>
        <tbody>
          {matches.map((m) => (
            <tr key={`${service}-${m.id}`} className="border-b border-[#1d2742]/60 last:border-0">
              <td className={`${tdCls} font-mono`}>{m.id}</td>
              <td className={tdCls}>{num(m.sep_arcsec, 2)}</td>
              <td className={tdCls}>{m.mag == null ? "—" : `${num(m.mag, 2)}${m.mag_band ? ` ${m.mag_band}` : ""}`}</td>
              <td className={tdCls}>{m.pm_ra == null || m.pm_dec == null ? "—" : `${num(m.pm_ra, 0)}, ${num(m.pm_dec, 0)}`}</td>
              <td className={tdCls}>{num(m.parallax, 2)}</td>
              <td className={tdCls}>
                {[m.otype, m.class, m.variable_flag && m.variable_flag !== "NOT_AVAILABLE" ? m.variable_flag : null].filter(Boolean).join(" · ") || "—"}
              </td>
              <td className={tdCls}>{m.epoch_propagated ? <span className="text-[#59d98e]">✓</span> : <span className="text-[#8a97b4]">no</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

export default function CrossmatchPanel({ inv }: { inv: Investigation }) {
  const live = isLive(inv);
  const [radius, setRadius] = useState(30);
  const [result, setResult] = useState<{ cm: CrossMatch; radius: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cm: CrossMatch | undefined = result?.cm ?? inv.crossmatch;
  const usedRadius = result?.radius ?? 30;

  const meanMjd = useMemo(
    () => (inv.visits.length ? inv.visits.reduce((s, v) => s + v.mjd_mean, 0) / inv.visits.length : undefined),
    [inv.visits],
  );

  const requery = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await crossmatch(inv.target.ra, inv.target.dec, radius, meanMjd);
      setResult({ cm: r, radius });
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  };

  // Predicted vs observed position for the nearest Gaia association.
  const gaiaLine = useMemo(() => {
    const g = [...(cm?.gaia?.matches ?? [])].sort((a, b) => a.sep_arcsec - b.sep_arcsec)[0];
    if (!g) return null;
    const track = inv.track ?? [];
    const pred =
      meanMjd !== undefined && track.length
        ? track.reduce((best, p) => (Math.abs(p.mjd - meanMjd) < Math.abs(best.mjd - meanMjd) ? p : best), track[0])
        : { ra: inv.target.ra, dec: inv.target.dec };
    const dra = ((((g.ra - pred.ra) % 360) + 540) % 360) - 180;
    const diff = Math.hypot(dra * Math.cos((pred.dec * Math.PI) / 180), g.dec - pred.dec) * 3600;
    return { g, pred, diff, fromTrack: track.length > 0 && meanMjd !== undefined };
  }, [cm, inv.track, inv.target.ra, inv.target.dec, meanMjd]);

  if (!cm) {
    return (
      <Card title="Catalog cross-match">
        <EmptyState title="Cross-match not available yet">Catalog queries run after the measurement stage.</EmptyState>
      </Card>
    );
  }

  return (
    <Card title="Catalog cross-match" subtitle="Associations with Gaia, SIMBAD, CatWISE and SkyBoT around the target position">
      <Note>
        An association within {usedRadius}″ is a <strong className="text-[#e6ebf5]">positional coincidence, not proof of
        identity</strong>. Separation is measured from the requested position{usedRadius === 30 && !result ? " (default match radius)" : ""}.
      </Note>

      <div className="mt-3 space-y-4">
        {SERVICES.map((s) => {
          const r = cm[s.key];
          return (
            <div key={s.key}>
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <h4 className="text-sm font-semibold text-[#e6ebf5]">{s.label}</h4>
                <StatusChip status={r?.status ?? "unavailable"} message={r?.message} />
                <span className="text-xs text-[#8a97b4]">{s.blurb}</span>
              </div>
              {r?.status !== "ok" ? (
                <p className="text-xs text-[#f2b84b]">
                  {r?.message ? r.message : r?.status === "error" ? "The service returned an error." : "The service was unavailable, so this check is missing — not evidence of a non-match."}
                </p>
              ) : (
                <MatchTable matches={r.matches} service={s.key} />
              )}
            </div>
          );
        })}
      </div>

      {gaiaLine && (
        <>
          <SectionTitle>Predicted vs observed position (nearest Gaia association)</SectionTitle>
          <p className="text-xs leading-relaxed text-[#e6ebf5]">
            Gaia <span className="font-mono">{gaiaLine.g.id}</span> lies {num(gaiaLine.g.sep_arcsec, 2)}″ from the requested position.{" "}
            {gaiaLine.g.epoch_propagated ? "Its position was propagated to the SPHEREx epoch. " : "Its position was not propagated to the SPHEREx epoch. "}
            Predicted {gaiaLine.fromTrack ? "position at the mean SPHEREx epoch" : "(requested) position"}:{" "}
            <span className="tabular-nums">{formatRA(gaiaLine.pred.ra)} {formatDec(gaiaLine.pred.dec)}</span>; Gaia:{" "}
            <span className="tabular-nums">{formatRA(gaiaLine.g.ra)} {formatDec(gaiaLine.g.dec)}</span>; difference{" "}
            <strong className="tabular-nums">{num(gaiaLine.diff, 2)}″</strong>.
          </p>
        </>
      )}

      <SectionTitle hint="Larger radii find more chance coincidences; smaller radii can miss a high-proper-motion match.">
        Match radius
      </SectionTitle>
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="range"
          min={1}
          max={180}
          step={1}
          value={radius}
          onChange={(e) => setRadius(Number(e.target.value))}
          aria-label="Match radius in arcseconds"
          className="min-w-[10rem] flex-1 accent-[#74c7da]"
          disabled={!live}
        />
        <span className="w-12 text-right text-xs tabular-nums text-[#e6ebf5]">{radius}″</span>
        <button type="button" className={btnPrimary} onClick={requery} disabled={!live || busy}>
          {busy ? "Querying…" : "Re-query"}
        </button>
      </div>
      {!live && (
        <p className="mt-1 text-xs text-[#8a97b4]">
          Re-querying needs the live service. This is a precomputed snapshot, so the radius control is disabled.
        </p>
      )}
      {error && (
        <div className="mt-2">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}
    </Card>
  );
}
