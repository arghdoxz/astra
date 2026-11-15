"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import HealthChip from "@/components/layout/HealthChip";

const LINKS = [
  { href: "/investigate", label: "Investigate" },
  { href: "/targets", label: "Targets" },
  { href: "/review", label: "Review" },
  { href: "/about", label: "About" },
];

function StarMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 1.5c.7 5.6 2.4 8.6 4.5 10.5 -2.1 1.9 -3.8 4.9 -4.5 10.5 -.7 -5.6 -2.4 -8.6 -4.5 -10.5C9.6 10.1 11.3 7.1 12 1.5Z" fill="#5ad1e6" />
      <path d="M1.5 12c5.6.7 8.6 2.4 10.5 4.5 1.9 -2.1 4.9 -3.8 10.5 -4.5 -5.6 -.7 -8.6 -2.4 -10.5 -4.5C10.1 9.6 7.1 11.3 1.5 12Z" fill="#5ad1e6" opacity=".35" />
    </svg>
  );
}

export default function Nav() {
  const pathname = usePathname();
  if (pathname === "/embed") return null; // iframe-friendly: no site chrome
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/85 backdrop-blur">
      <div className="page flex flex-wrap items-center gap-x-6 gap-y-1 py-2.5">
        <Link href="/" className="flex items-center gap-2 text-fg no-underline hover:no-underline" aria-label="ASTRA home">
          <StarMark />
          <span className="text-[1.05rem] font-semibold tracking-[0.22em]">ASTRA</span>
        </Link>
        <nav aria-label="Primary" className="order-3 flex w-full gap-1 sm:order-none sm:w-auto sm:flex-1">
          {LINKS.map((l) => {
            const active = pathname === l.href || pathname.startsWith(l.href + "/");
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 text-sm no-underline transition-colors duration-150 hover:no-underline ${
                  active ? "bg-panel2 text-fg" : "text-muted hover:text-fg"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto min-w-0 sm:ml-0">
          <HealthChip />
        </div>
      </div>
    </header>
  );
}
