import { Suspense } from "react";
import type { Metadata } from "next";
import InvestigateClient from "./InvestigateClient";

export const metadata: Metadata = {
  title: "Investigate · ASTRA",
  description: "Investigate a position on the sky with real SPHEREx observations over time.",
};

export default function InvestigatePage() {
  return (
    <main>
      <Suspense
        fallback={
          <div className="page py-10 text-sm text-muted" role="status">
            Loading investigation…
          </div>
        }
      >
        <InvestigateClient />
      </Suspense>
    </main>
  );
}
