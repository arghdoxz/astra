"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import HealthChip from "@/components/layout/HealthChip";

const LINKS = [
  { href: "/investigate", label: "Investigate" },
  { href: "/targets", label: "Targets" },
  { href: "/review", label: "Review" },
  { href: "/about", label: "About" },
];

function Mark() {
  // A reticle: the thing ASTRA puts around a measured source.
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="#ffb547" strokeWidth="1.4">
      <path d="M1 6V1h5M14 1h5v5M19 14v5h-5M6 19H1v-5" />
      <circle cx="10" cy="10" r="2" fill="#ffb547" stroke="none" />
    </svg>
  );
}

/** Live UTC and Modified Julian Date: the time system every SPHEREx exposure is stamped in. */
function Clock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const tick = () => setNow(new Date());
    const first = setTimeout(tick, 0); // client-only, avoids a hydration mismatch
    const id = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, []);
  if (!now) return <span className="hidden w-[15rem] lg:block" />;
  const mjd = now.getTime() / 86400000 + 40587;
  return (
    <span className="mono hidden text-[0.7rem] tracking-wider text-muted lg:block" title="Coordinated Universal Time and Modified Julian Date">
      UTC {now.toISOString().slice(11, 19)} <span className="mx-1.5 text-line">|</span> MJD {mjd.toFixed(4)}
    </span>
  );
}

export default function Nav() {
  const pathname = usePathname();
  if (pathname === "/embed") return null; // iframe-friendly: no site chrome
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-[#04060b]">
      <div className="page flex flex-wrap items-center gap-x-6 gap-y-1 py-2">
        <Link href="/" className="flex items-center gap-2.5 text-fg no-underline hover:no-underline" aria-label="ASTRA home">
          <Mark />
          <span className="font-[family-name:var(--font-display)] text-[1.1rem] font-semibold tracking-[0.28em]">ASTRA</span>
        </Link>
        <nav aria-label="Primary" className="order-3 flex w-full gap-0.5 sm:order-none sm:w-auto sm:flex-1">
          {LINKS.map((l) => {
            const active = pathname === l.href || pathname.startsWith(l.href + "/");
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={`mono border-b px-3 py-1.5 text-[0.72rem] uppercase tracking-[0.12em] no-underline transition-colors duration-150 hover:no-underline ${
                  active ? "border-sodium text-fg" : "border-transparent text-muted hover:text-fg"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <Clock />
        <div className="ml-auto min-w-0 sm:ml-0">
          <HealthChip />
        </div>
      </div>
    </header>
  );
}
