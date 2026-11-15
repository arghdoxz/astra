"use client";

import { usePathname } from "next/navigation";
import HealthChip from "@/components/layout/HealthChip";

export default function Footer() {
  const pathname = usePathname();
  if (pathname === "/embed") return null;
  return (
    <footer className="mt-12 border-t border-fg bg-panel py-6 text-sm text-muted">
      <div className="page grid gap-3 md:grid-cols-[1fr_auto]">
        <div className="space-y-1.5">
          <p>ASTRA is an independent NASA Space Apps 2026 entry. It is not affiliated with or endorsed by NASA.</p>
          <p>
            Data: SPHEREx DR1 and QR3 (NASA/IPAC IRSA), Gaia DR3 (ESA), SIMBAD (CDS), CatWISE2020, SkyBoT (IMCCE). The plate drawn behind the pages is an illustration, not survey
            data.
          </p>
        </div>
        <HealthChip />
      </div>
    </footer>
  );
}
