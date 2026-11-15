import type { ReactNode } from "react";

type BannerTone = "info" | "warn" | "danger" | "ok";

// An archive note pinned to the sheet: paper, a full ink border in the tone colour, a typed label.
const STYLES: Record<BannerTone, { box: string; label: string; word: string }> = {
  info: { box: "border-accent", label: "text-accent", word: "Note" },
  warn: { box: "border-warn", label: "text-warn", word: "Caution" },
  danger: { box: "border-bad", label: "text-bad", word: "Problem" },
  ok: { box: "border-good", label: "text-good", word: "OK" },
};

export default function Banner({
  tone = "info",
  title,
  children,
  action,
  role,
}: {
  tone?: BannerTone;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  role?: "status" | "alert";
}) {
  const s = STYLES[tone];
  return (
    <div role={role ?? (tone === "danger" ? "alert" : "status")} className={`fade-in flex gap-3 items-start border bg-panel px-3.5 py-2.5 text-sm ${s.box}`}>
      <span aria-hidden className={`mono shrink-0 font-bold ${s.label}`}>{s.word}:</span>
      <div className="min-w-0 flex-1">
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className="text-fg">{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
