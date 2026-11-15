import type { ReactNode } from "react";

type BannerTone = "info" | "warn" | "danger" | "ok";

const STYLES: Record<BannerTone, { box: string; dot: string }> = {
  info: { box: "border-accent/40 bg-accent/5", dot: "bg-accent" },
  warn: { box: "border-warn/45 bg-warn/8", dot: "bg-warn" },
  danger: { box: "border-bad/45 bg-bad/8", dot: "bg-bad" },
  ok: { box: "border-good/40 bg-good/5", dot: "bg-good" },
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
    <div role={role ?? (tone === "danger" ? "alert" : "status")} className={`fade-in flex gap-3 items-start rounded-lg border px-3.5 py-2.5 text-sm ${s.box}`}>
      <span aria-hidden className={`mt-[7px] h-2 w-2 shrink-0 rounded-full ${s.dot}`} />
      <div className="min-w-0 flex-1">
        {title && <div className="font-medium">{title}</div>}
        {children && <div className="text-[#c5cde0]">{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
