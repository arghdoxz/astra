"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/investigate", label: "Investigate" },
  { href: "/targets", label: "Targets" },
  { href: "/review", label: "Review" },
  { href: "/about", label: "About" },
];

export default function Nav() {
  const pathname = usePathname();
  if (pathname === "/embed") return null; // iframe-friendly: no site chrome
  return (
    <header className="sticky top-0 z-40 border-b border-fg bg-panel">
      <div className="page flex flex-wrap items-baseline gap-x-8 gap-y-1 py-3">
        <Link href="/" className="serif text-[1.45rem] font-bold leading-none text-fg no-underline hover:text-fg" aria-label="ASTRA home">
          ASTRA
        </Link>
        <nav aria-label="Primary" className="flex flex-wrap gap-x-5 gap-y-1">
          {LINKS.map((l) => {
            const active = pathname === l.href || pathname.startsWith(l.href + "/");
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={`text-[0.95rem] no-underline decoration-2 underline-offset-[6px] hover:text-fg hover:underline ${
                  active ? "text-fg underline decoration-pencil" : "text-muted"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
