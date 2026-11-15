import { Suspense } from "react";
import type { Metadata } from "next";
import EmbedClient from "./EmbedClient";

export const metadata: Metadata = {
  title: "ASTRA viewer (embed)",
  description: "Embeddable SPHEREx epoch viewer.",
};

export default function EmbedPage() {
  return (
    <main>
      <Suspense
        fallback={
          <div className="p-4 text-sm text-muted" role="status">
            Loading…
          </div>
        }
      >
        <EmbedClient />
      </Suspense>
    </main>
  );
}
