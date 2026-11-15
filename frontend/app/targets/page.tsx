import type { Metadata } from "next";
import TargetCard from "@/components/targets/TargetCard";
import { TARGETS } from "@/lib/targets";

export const metadata: Metadata = {
  title: "Target library · ASTRA",
  description: "Five well-studied objects used to validate ASTRA against known answers.",
};

export default function TargetsPage() {
  return (
    <main className="page space-y-8 py-8">
      <header className="max-w-3xl space-y-3">
        <h1 className="serif text-3xl font-semibold">Target library</h1>
        <p className="max-w-[62ch] text-fg">
          These five objects are validation scenarios: each is well studied, so we know roughly what ASTRA should find and can check that it finds it, or says honestly that it cannot. Open any of them to see
          the full workflow, or use the search box for any other position.
        </p>
      </header>
      <div className="flex flex-col gap-4">
        {TARGETS.map((t) => (
          <TargetCard key={t.slug} target={t} detailed />
        ))}
      </div>
    </main>
  );
}
