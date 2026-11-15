import Link from "next/link";
import SearchBar from "@/components/search/SearchBar";
import TargetCard from "@/components/targets/TargetCard";
import { TARGETS } from "@/lib/targets";

const STEPS = [
  { t: "Resolve", d: "Your name or coordinates become a sky position (with proper motion, if the object moves)." },
  { t: "SPHEREx exposures", d: "ASTRA finds every public SPHEREx DR1 and QR3 exposure of that spot." },
  { t: "Stacks & difference images", d: "Exposures are grouped into ~6-month visits, stacked, and subtracted to reveal change." },
  { t: "Measurements", d: "Calibrated brightness, position, a 0.75–5 µm spectrum and a proper-motion fit." },
  { t: "Evidence", d: "Every number is checked against thresholds, SPHEREx's contamination flags and catalogues (Gaia, SIMBAD, CatWISE, SkyBoT)." },
  { t: "AI explanation", d: "An AI assistant explains the measured evidence in plain language. It may not invent numbers." },
  { t: "Human review", d: "You can record your own verdict. Nothing is called a discovery without people checking it." },
];

export default function Home() {
  return (
    <main>
      <section className="starfield border-b border-line">
        <div className="page py-12 sm:py-20">
          <p className="eyebrow mb-3">SPHEREx time-domain explorer</p>
          <h1 className="max-w-3xl text-3xl font-semibold leading-tight tracking-tight sm:text-5xl sm:leading-[1.12]">
            See how the infrared sky changes, measured from real SPHEREx data, with evidence you can check.
          </h1>
          <p className="mt-5 max-w-2xl text-base text-[#c5cde0] sm:text-lg">
            NASA&apos;s SPHEREx telescope maps the whole sky every six months in 102 infrared colours. Enter any position and ASTRA shows how that spot changed over time,
            which objects moved or varied, and how sure we can be, with every measurement and its uncertainty open to inspection.
          </p>
          <div className="card card-pad mt-8 max-w-3xl bg-panel/90 backdrop-blur">
            <SearchBar />
          </div>
        </div>
      </section>

      <section className="page py-12" aria-labelledby="library">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 id="library" className="text-xl font-semibold">
              Target library
            </h2>
            <p className="text-sm text-muted">Five well-studied objects that exercise different parts of the pipeline.</p>
          </div>
          <Link href="/targets" className="text-sm">
            Why these five? →
          </Link>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {TARGETS.map((t) => (
            <TargetCard key={t.slug} target={t} />
          ))}
        </div>
      </section>

      <section className="page pb-12" aria-labelledby="how">
        <h2 id="how" className="mb-5 text-xl font-semibold">
          How it works
        </h2>
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <li key={s.t} className="card card-pad">
              <span className="mono text-xs text-accent">{String(i + 1).padStart(2, "0")}</span>
              <h3 className="mt-1 font-medium">{s.t}</h3>
              <p className="mt-1 text-sm text-muted">{s.d}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="page pb-6" aria-labelledby="honesty">
        <div className="card card-pad border-warn/30">
          <h2 id="honesty" className="h-sec text-warn">
            What ASTRA does not do
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-[#c5cde0]">
            ASTRA never announces discoveries. The strongest statement it can make about an unexplained change is &ldquo;needs human review&rdquo;. Confidence levels are transparent rules, not probabilities, and
            limitations such as saturated stars and approximate difference imaging are shown wherever they matter.{" "}
            <Link href="/about">Read the limitations</Link>. ASTRA is an independent project, not affiliated with or endorsed by NASA.
          </p>
        </div>
      </section>
    </main>
  );
}
