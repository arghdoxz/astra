import type { Metadata } from "next";
import HistoryList from "@/components/panels/HistoryList";
import ReviewQueue from "@/components/panels/ReviewQueue";

export const metadata: Metadata = {
  title: "Review · ASTRA",
  description: "Citizen-science review: look at the evidence and record your verdict.",
};

export default function ReviewPage() {
  return (
    <main className="page space-y-8 py-8">
      <header className="max-w-3xl space-y-2">
        <h1 className="text-2xl font-semibold">Review</h1>
        <p className="text-[#c5cde0]">
          ASTRA scores evidence, but people decide. Open an item, look at the images, measurements and catalogue matches, and record whether you think it is real, an artifact, already known, or unsure. Your
          verdicts are tallied next to the automatic classification; they never change it.
        </p>
      </header>
      <section aria-labelledby="queue" className="space-y-3">
        <h2 id="queue" className="h-sec">
          Review queue
        </h2>
        <ReviewQueue />
      </section>
      <section aria-labelledby="history" className="space-y-3">
        <h2 id="history" className="h-sec">
          Recent investigations
        </h2>
        <HistoryList />
      </section>
    </main>
  );
}
