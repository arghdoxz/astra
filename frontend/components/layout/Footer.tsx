"use client";

import { usePathname } from "next/navigation";

export default function Footer() {
  const pathname = usePathname();
  if (pathname === "/embed") return null;
  return (
    <footer className="mt-10 border-t border-line bg-[#04060b]/90 py-6 text-xs text-muted">
      <div className="page flex flex-wrap justify-between gap-x-6 gap-y-2">
        <span>ASTRA is an independent NASA Space Apps 2026 entry. Not affiliated with or endorsed by NASA.</span>
        <span>Data: SPHEREx DR1/QR3 (NASA/IPAC IRSA) · Gaia DR3 (ESA) · SIMBAD (CDS) · CatWISE2020 · SkyBoT (IMCCE)</span>
        <span className="w-full opacity-70">The animated sky behind the pages is a decorative illustration, not survey data.</span>
      </div>
    </footer>
  );
}
