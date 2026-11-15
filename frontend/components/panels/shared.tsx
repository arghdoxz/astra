"use client";

import type { ReactNode } from "react";
import type { Classification, Confidence, ServiceStatus, StatementKind } from "@/lib/types";

/* ------------------------------------------------------------------ */
/* Safe local formatters (null-tolerant, no dependency on other agents) */
/* ------------------------------------------------------------------ */

export function num(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

/** Significant-figure formatter, good for fluxes spanning orders of magnitude. */
export function sigfig(v: number | null | undefined, sf = 3): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  if (v === 0) return "0";
  const a = Math.abs(v);
  if (a >= 1e5 || a < 1e-2) return v.toExponential(sf - 1);
  return Number(v.toPrecision(sf)).toString();
}

export function mjdToDate(mjd: number | null | undefined): string {
  if (mjd === null || mjd === undefined || !Number.isFinite(mjd)) return "—";
  const d = new Date((mjd - 40587) * 86400000);
  return Number.isNaN(d.getTime()) ? "—" : d.toISOString().slice(0, 10);
}

export function errMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  return "Unexpected error";
}

/** Accept either an array or an { items: [] } envelope. */
export function toArray<T>(r: unknown): T[] {
  if (Array.isArray(r)) return r as T[];
  if (r && typeof r === "object" && Array.isArray((r as { items?: unknown }).items)) {
    return (r as { items: T[] }).items;
  }
  return [];
}

/* ------------------------------------------------------------------ */
/* Layout primitives                                                    */
/* ------------------------------------------------------------------ */

export function Card({
  title,
  subtitle,
  right,
  children,
  className = "",
  id,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  children?: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section
      id={id}
      className={`rounded-sm border border-[#1d2742] bg-[#111830] p-3 text-[#e6ebf5] sm:p-4 ${className}`}
    >
      {(title || right) && (
        <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            {title && <h3 className="text-sm font-semibold tracking-wide text-[#e6ebf5]">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-[#8a97b4]">{subtitle}</p>}
          </div>
          {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function SectionTitle({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="mb-1.5 mt-3 first:mt-0">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-[#8a97b4]">{children}</h4>
      {hint && <p className="mt-0.5 text-xs text-[#8a97b4]">{hint}</p>}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  tone = "neutral",
}: {
  title: ReactNode;
  children?: ReactNode;
  tone?: "neutral" | "warn";
}) {
  const border = tone === "warn" ? "border-[#f2b84b]/40" : "border-[#1d2742]";
  return (
    <div
      role="status"
      className={`rounded-sm border border-dashed ${border} bg-[#0a0f1c]/60 px-3 py-4 text-center`}
    >
      <p className="text-sm font-medium text-[#e6ebf5]">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-prose text-xs leading-relaxed text-[#8a97b4]">{children}</div>}
    </div>
  );
}

export function Note({ children, tone = "muted" }: { children: ReactNode; tone?: "muted" | "amber" | "cyan" }) {
  const cls =
    tone === "amber"
      ? "border-[#f2b84b]/40 bg-[#f2b84b]/10 text-[#f2d9a0]"
      : tone === "cyan"
        ? "border-[#74c7da]/30 bg-[#74c7da]/10 text-[#bfeaf3]"
        : "border-[#1d2742] bg-[#0a0f1c]/60 text-[#8a97b4]";
  return <p className={`rounded-sm border px-2.5 py-1.5 text-xs leading-relaxed ${cls}`}>{children}</p>;
}

export function Pill({
  children,
  className = "",
  title,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-[11px] font-medium leading-tight ${className}`}
    >
      {children}
    </span>
  );
}

/** Shared control class strings so every control looks consistent and has a focus ring. */
export const btn =
  "inline-flex items-center justify-center gap-1.5 rounded-sm border border-[#1d2742] bg-[#0a0f1c] px-2.5 py-1.5 text-xs font-medium text-[#e6ebf5] transition-colors hover:border-[#74c7da]/60 hover:text-[#74c7da] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#74c7da] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-[#1d2742] disabled:hover:text-[#e6ebf5]";
export const btnPrimary =
  "inline-flex items-center justify-center gap-1.5 rounded-sm border border-[#74c7da]/60 bg-[#74c7da]/15 px-3 py-1.5 text-xs font-semibold text-[#74c7da] transition-colors hover:bg-[#74c7da]/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#74c7da] disabled:cursor-not-allowed disabled:opacity-50";
export const inputCls =
  "w-full rounded-sm border border-[#1d2742] bg-[#0a0f1c] px-2 py-1.5 text-xs text-[#e6ebf5] placeholder:text-[#8a97b4]/70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#74c7da]";

/** Small segmented toggle used by plots (real buttons, aria-pressed). */
export function Toggle({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex overflow-hidden rounded-sm border border-[#1d2742]">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={`px-2.5 py-1 text-xs font-medium focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[#74c7da] ${
            value === o.value ? "bg-[#74c7da]/20 text-[#74c7da]" : "bg-[#0a0f1c] text-[#8a97b4] hover:text-[#e6ebf5]"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Badges                                                               */
/* ------------------------------------------------------------------ */

const KIND_META: Record<StatementKind, { label: string; cls: string; desc: string }> = {
  measured: {
    label: "Measured",
    cls: "border-[#74c7da]/40 bg-[#74c7da]/10 text-[#74c7da]",
    desc: "A number or fact computed directly from SPHEREx data.",
  },
  catalog: {
    label: "Catalog",
    cls: "border-[#f2b84b]/40 bg-[#f2b84b]/10 text-[#f2b84b]",
    desc: "Information from an external catalog (Gaia, SIMBAD, CatWISE, SkyBoT).",
  },
  interpretation: {
    label: "Interpretation",
    cls: "border-[#8fa8ff]/40 bg-[#8fa8ff]/10 text-[#a9bbff]",
    desc: "A reading of the measurements; reasonable but not certain.",
  },
  hypothesis: {
    label: "Hypothesis",
    cls: "border-[#c79bff]/40 bg-[#c79bff]/10 text-[#d3b3ff]",
    desc: "A possible explanation that has not been tested.",
  },
  missing: {
    label: "Missing evidence",
    cls: "border-[#8a97b4]/50 border-dashed bg-transparent text-[#8a97b4]",
    desc: "Something that would help but is not available.",
  },
};

export const KIND_ORDER: StatementKind[] = ["measured", "catalog", "interpretation", "hypothesis", "missing"];
export const kindDescription = (k: StatementKind) => KIND_META[k].desc;

export function KindTag({ kind }: { kind: StatementKind }) {
  const m = KIND_META[kind] ?? KIND_META.interpretation;
  return (
    <span
      title={m.desc}
      className={`inline-block shrink-0 rounded border px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide ${m.cls}`}
    >
      {m.label}
    </span>
  );
}

const CONF_META: Record<Confidence, { label: string; cls: string; bars: number }> = {
  insufficient: {
    label: "Insufficient evidence",
    cls: "border-dashed border-[#8a97b4]/60 bg-transparent text-[#8a97b4]",
    bars: 0,
  },
  low: { label: "Low confidence tier", cls: "border-[#f2b84b]/50 bg-[#f2b84b]/10 text-[#f2b84b]", bars: 1 },
  moderate: { label: "Moderate confidence tier", cls: "border-[#74c7da]/50 bg-[#74c7da]/10 text-[#74c7da]", bars: 2 },
  strong: { label: "Strong confidence tier", cls: "border-[#59d98e]/50 bg-[#59d98e]/10 text-[#59d98e]", bars: 3 },
};

/** Confidence is a rule-based tier (never a percentage). */
export function ConfidenceBadge({ confidence, reason }: { confidence: Confidence; reason?: string }) {
  const m = CONF_META[confidence] ?? CONF_META.insufficient;
  return (
    <span className="inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-1">
      <span
        title={reason}
        className={`inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-xs font-semibold ${m.cls}`}
      >
        <span aria-hidden className="inline-flex items-end gap-px">
          {[1, 2, 3].map((i) => (
            <span
              key={i}
              className={`inline-block w-0.5 rounded-sm ${i <= m.bars ? "bg-current" : "bg-current opacity-25"}`}
              style={{ height: 4 + i * 2 }}
            />
          ))}
        </span>
        {m.label}
      </span>
      {reason && <span className="text-xs text-[#8a97b4]">{reason}</span>}
    </span>
  );
}

const CLASS_TONE: Record<Classification, string> = {
  insufficient_data: "border-[#8a97b4]/50 text-[#8a97b4]",
  likely_artifact: "border-[#f26b6b]/50 bg-[#f26b6b]/10 text-[#f58a8a]",
  solar_system_object: "border-[#f2b84b]/50 bg-[#f2b84b]/10 text-[#f2b84b]",
  known_high_pm_star: "border-[#74c7da]/50 bg-[#74c7da]/10 text-[#74c7da]",
  known_variable: "border-[#74c7da]/50 bg-[#74c7da]/10 text-[#74c7da]",
  known_no_change: "border-[#59d98e]/40 bg-[#59d98e]/10 text-[#59d98e]",
  no_significant_change: "border-[#59d98e]/40 bg-[#59d98e]/10 text-[#59d98e]",
  unexplained_needs_review: "border-[#e05bd1]/50 bg-[#e05bd1]/10 text-[#f08be3]",
  low_confidence_change: "border-[#f2b84b]/40 bg-[#f2b84b]/5 text-[#f2b84b]",
};

export function ClassificationBadge({ classification, label }: { classification: Classification; label: string }) {
  const cls = CLASS_TONE[classification] ?? "border-[#8a97b4]/50 text-[#8a97b4]";
  return (
    <span className={`inline-flex items-center rounded-sm border px-2 py-0.5 text-xs font-semibold ${cls}`}>
      {label}
    </span>
  );
}

export function NoveltyChip({ novelty }: { novelty: "catalogued" | "uncatalogued" | "unknown" }) {
  const m = {
    catalogued: {
      t: "Catalogued",
      d: "At least one catalog association exists within the match radius.",
      c: "text-[#74c7da] border-[#74c7da]/40",
    },
    uncatalogued: {
      t: "No catalog association",
      d: "All identity services answered and none matched within the match radius.",
      c: "text-[#f2b84b] border-[#f2b84b]/40",
    },
    unknown: {
      t: "Catalog status unknown",
      d: "At least one catalog service was unavailable, so novelty cannot be judged.",
      c: "text-[#8a97b4] border-[#8a97b4]/40 border-dashed",
    },
  }[novelty];
  return (
    <span title={m.d} className={`inline-flex items-center rounded-sm border px-2 py-0.5 text-[11px] font-medium ${m.c}`}>
      {m.t}
    </span>
  );
}

export function StatusChip({
  status,
  label,
  message,
}: {
  status: ServiceStatus | string;
  label?: string;
  message?: string | null;
}) {
  const tone =
    status === "ok"
      ? "border-[#59d98e]/40 bg-[#59d98e]/10 text-[#59d98e]"
      : status === "unavailable"
        ? "border-[#f2b84b]/40 bg-[#f2b84b]/10 text-[#f2b84b]"
        : "border-[#f26b6b]/40 bg-[#f26b6b]/10 text-[#f58a8a]";
  const glyph = status === "ok" ? "●" : status === "unavailable" ? "◌" : "✖";
  return (
    <span
      title={message ?? undefined}
      className={`inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-[11px] font-medium ${tone}`}
    >
      <span aria-hidden>{glyph}</span>
      {label && <span>{label}</span>}
      <span className="opacity-80">{status}</span>
    </span>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-sm border border-[#f26b6b]/40 bg-[#f26b6b]/10 px-2.5 py-1.5 text-xs text-[#f58a8a]">
      {children}
    </p>
  );
}

/** Scrollable table wrapper so tables never force horizontal page scroll at 360 px. */
export function TableWrap({ children }: { children: ReactNode }) {
  return <div className="-mx-1 overflow-x-auto px-1">{children}</div>;
}
export const thCls =
  "whitespace-nowrap px-2 py-1 text-left text-[11px] font-semibold uppercase tracking-wide text-[#8a97b4]";
export const tdCls = "whitespace-nowrap px-2 py-1 align-top text-xs text-[#e6ebf5] tabular-nums";
