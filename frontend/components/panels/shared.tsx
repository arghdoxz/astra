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
    <section id={id} className={`border border-line bg-panel p-4 text-fg sm:p-5 ${className}`}>
      {(title || right) && (
        <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            {title && <h2 className="serif text-lg font-semibold leading-snug text-fg">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
          </div>
          {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

/** A divided section inside a card: a rule above, a serif heading, optional hint. */
export function SectionTitle({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="mb-2 mt-5 border-t border-line pt-3 first:mt-0 first:border-t-0 first:pt-0">
      <h4 className="serif text-base font-semibold text-fg">{children}</h4>
      {hint && <p className="mt-0.5 text-sm text-muted">{hint}</p>}
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
  const border = tone === "warn" ? "border-warn" : "border-line";
  return (
    <div role="status" className={`border border-dashed ${border} bg-panel2 px-3 py-4 text-center`}>
      <p className="text-sm font-medium text-fg">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-prose text-sm leading-relaxed text-muted">{children}</div>}
    </div>
  );
}

export function Note({ children, tone = "muted" }: { children: ReactNode; tone?: "muted" | "amber" | "cyan" }) {
  const cls =
    tone === "amber"
      ? "border-warn bg-panel text-fg"
      : tone === "cyan"
        ? "border-accent bg-panel text-fg"
        : "border-line bg-panel2 text-muted";
  return <p className={`border border-l-4 px-3 py-2 text-sm leading-relaxed ${cls}`}>{children}</p>;
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
    <span title={title} className={`chip ${className}`}>
      {children}
    </span>
  );
}

/** Shared control class strings; they reuse the global .btn / .input classes. */
export const btn = "btn btn-sm";
export const btnPrimary = "btn btn-sm btn-primary";
export const inputCls = "input";

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
    <div role="group" aria-label={label} className="inline-flex">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className="btn btn-sm -ml-px first:ml-0"
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
    cls: "chip-cyan",
    desc: "A number or fact computed directly from SPHEREx data.",
  },
  catalog: {
    label: "Catalog",
    cls: "chip-amber",
    desc: "Information from an external catalog (Gaia, SIMBAD, CatWISE, SkyBoT).",
  },
  interpretation: {
    label: "Interpretation",
    cls: "",
    desc: "A reading of the measurements; reasonable but not certain.",
  },
  hypothesis: {
    label: "Hypothesis",
    cls: "chip-mag",
    desc: "A possible explanation that has not been tested.",
  },
  missing: {
    label: "Missing evidence",
    cls: "border-dashed",
    desc: "Something that would help but is not available.",
  },
};

export const KIND_ORDER: StatementKind[] = ["measured", "catalog", "interpretation", "hypothesis", "missing"];
export const kindDescription = (k: StatementKind) => KIND_META[k].desc;

export function KindTag({ kind }: { kind: StatementKind }) {
  const m = KIND_META[kind] ?? KIND_META.interpretation;
  return (
    <span title={m.desc} className={`chip shrink-0 ${m.cls}`}>
      {m.label}
    </span>
  );
}

const CONF_META: Record<Confidence, { label: string; cls: string; bars: number }> = {
  insufficient: { label: "Insufficient evidence", cls: "border-dashed", bars: 0 },
  low: { label: "Low confidence tier", cls: "chip-amber", bars: 1 },
  moderate: { label: "Moderate confidence tier", cls: "chip-cyan", bars: 2 },
  strong: { label: "Strong confidence tier", cls: "chip-green", bars: 3 },
};

/** Confidence is a rule-based tier (never a percentage). */
export function ConfidenceBadge({ confidence, reason }: { confidence: Confidence; reason?: string }) {
  const m = CONF_META[confidence] ?? CONF_META.insufficient;
  return (
    <span className="inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-1">
      <span title={reason} className={`chip font-semibold ${m.cls}`}>
        <span aria-hidden className="inline-flex items-end gap-px">
          {[1, 2, 3].map((i) => (
            <span
              key={i}
              className={`inline-block w-0.5 ${i <= m.bars ? "bg-current" : "bg-current opacity-25"}`}
              style={{ height: 4 + i * 2 }}
            />
          ))}
        </span>
        {m.label}
      </span>
      {reason && <span className="text-sm text-muted">{reason}</span>}
    </span>
  );
}

const CLASS_TONE: Record<Classification, string> = {
  insufficient_data: "border-dashed",
  likely_artifact: "chip-red",
  solar_system_object: "chip-amber",
  known_high_pm_star: "chip-cyan",
  known_variable: "chip-cyan",
  known_no_change: "chip-green",
  no_significant_change: "chip-green",
  unexplained_needs_review: "chip-mag",
  low_confidence_change: "chip-amber",
};

export function ClassificationBadge({ classification, label }: { classification: Classification; label: string }) {
  const cls = CLASS_TONE[classification] ?? "";
  return <span className={`chip font-semibold ${cls}`}>{label}</span>;
}

export function NoveltyChip({ novelty }: { novelty: "catalogued" | "uncatalogued" | "unknown" }) {
  const m = {
    catalogued: {
      t: "Catalogued",
      d: "At least one catalog association exists within the match radius.",
      c: "chip-cyan",
    },
    uncatalogued: {
      t: "No catalog association",
      d: "All identity services answered and none matched within the match radius.",
      c: "chip-amber",
    },
    unknown: {
      t: "Catalog status unknown",
      d: "At least one catalog service was unavailable, so novelty cannot be judged.",
      c: "border-dashed",
    },
  }[novelty];
  return (
    <span title={m.d} className={`chip ${m.c}`}>
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
  const tone = status === "ok" ? "chip-green" : status === "unavailable" ? "chip-amber" : "chip-red";
  const glyph = status === "ok" ? "✓" : status === "unavailable" ? "–" : "×";
  return (
    <span title={message ?? undefined} className={`chip ${tone}`}>
      <span aria-hidden>{glyph}</span>
      {label && <span>{label}</span>}
      <span>{status}</span>
    </span>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="border border-l-4 border-pencil bg-panel px-3 py-2 text-sm text-pencil">
      {children}
    </p>
  );
}

/** Scrollable table wrapper so tables never force horizontal page scroll at 360 px. */
export function TableWrap({ children }: { children: ReactNode }) {
  return <div className="-mx-1 overflow-x-auto px-1">{children}</div>;
}
export const thCls = "whitespace-nowrap px-2 py-1.5 text-left text-xs font-semibold text-muted";
export const tdCls = "mono whitespace-nowrap px-2 py-1.5 align-top text-sm text-fg tabular-nums";
