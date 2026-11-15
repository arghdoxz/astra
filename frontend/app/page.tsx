import Link from "next/link";
import SearchBar from "@/components/search/SearchBar";
import BlinkPlate from "@/components/targets/BlinkPlate";
import { TARGETS, targetHref } from "@/lib/targets";
import { formatDec, formatRA } from "@/lib/format";

const STEPS = [
  { t: "Resolve", d: "Name or coordinates to a sky position, with proper motion if the object moves." },
  { t: "Fetch", d: "Every public SPHEREx DR1 and QR3 exposure of that spot, from NASA/IPAC IRSA." },
  { t: "Stack", d: "Exposures grouped into ~6-month visits, stacked and differenced." },
  { t: "Measure", d: "Brightness, position, a 0.75–5 µm spectrum and a proper-motion fit." },
  { t: "Check", d: "Thresholds, SPHEREx artifact flags, blends, Gaia, SIMBAD, CatWISE, SkyBoT." },
  { t: "Explain", d: "An AI explainer restates the measured evidence. It cannot add numbers." },
  { t: "Review", d: "People record verdicts. Nothing is called a discovery." },
];

export default function Home() {
  return (
    <main>
      <section className="border-b border-line">
        <div className="page grid gap-10 py-12 sm:py-16 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] lg:items-center">
          <div>
            <p className="eyebrow mb-4">
              SPHEREx · DR1 + QR3 · 102 channels · 0.75–5.0 <span className="normal-case">µm</span>
            </p>
            <h1 className="max-w-2xl font-[family-name:var(--font-display)] text-4xl font-semibold leading-[1.02] tracking-tight sm:text-6xl">
              Watch the infrared sky change.
              <span className="block text-muted">Then check whether it really did.</span>
            </h1>
            <p className="mt-6 max-w-xl text-base text-[#c5cde0]">
              SPHEREx images the whole sky every six months. Give ASTRA a position and it pulls every exposure of that spot, blinks the visits, predicts where each star should be,
              and grades what changed against the catalogues, with the uncertainty and the reasons to doubt it on screen.
            </p>
            <div className="card frame mt-8 max-w-2xl p-4">
              <SearchBar />
            </div>
          </div>
          <BlinkPlate />
        </div>
      </section>

      <section className="page py-12" aria-labelledby="library">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <h2 id="library" className="rule-label flex-1">
            Observing list · five validation targets
          </h2>
          <Link href="/targets" className="mono text-[0.72rem] uppercase tracking-[0.12em]">
            Why these five →
          </Link>
        </div>
        <ol className="border-t border-line">
          {TARGETS.map((t, k) => (
            <li key={t.slug} className="border-b border-line">
              <Link
                href={targetHref(t)}
                className="group grid grid-cols-[2rem_1fr_auto] items-baseline gap-x-4 gap-y-1 px-1 py-3.5 text-fg no-underline transition-colors hover:bg-[#0b1220]/80 hover:no-underline md:grid-cols-[2rem_13rem_1fr_15rem_6rem]"
              >
                <span className="mono text-xs text-muted">{String(k + 1).padStart(2, "0")}</span>
                <span className="font-[family-name:var(--font-display)] text-lg font-semibold leading-tight">{t.name}</span>
                <span className="col-start-2 text-sm text-muted md:col-start-auto">{t.classification}</span>
                <span className="mono col-start-2 text-xs text-muted md:col-start-auto">
                  {formatRA(t.ra)} {formatDec(t.dec)}
                </span>
                <span className="mono col-start-3 row-start-1 text-right text-[0.72rem] uppercase tracking-[0.12em] text-sodium opacity-70 transition-opacity group-hover:opacity-100 md:col-start-auto md:row-start-auto">
                  Open →
                </span>
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <section className="page pb-12" aria-labelledby="how">
        <h2 id="how" className="rule-label mb-5">
          Pipeline
        </h2>
        <ol className="grid border-l border-t border-line sm:grid-cols-2 lg:grid-cols-7">
          {STEPS.map((s, i) => (
            <li key={s.t} className="border-b border-r border-line bg-[#060a12]/85 p-4">
              <span className="mono text-[0.68rem] text-sodium">{String(i + 1).padStart(2, "0")}</span>
              <h3 className="mt-1 font-[family-name:var(--font-display)] text-base font-semibold uppercase tracking-wider">{s.t}</h3>
              <p className="mt-1 text-[0.82rem] leading-snug text-muted">{s.d}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="page pb-6" aria-labelledby="honesty">
        <h2 id="honesty" className="rule-label mb-3 !text-warn">
          What ASTRA will not do
        </h2>
        <p className="max-w-3xl text-sm text-[#c5cde0]">
          ASTRA never announces discoveries. The strongest thing it can say about an unexplained change is &ldquo;needs human review&rdquo;. Confidence levels are written rules, not probabilities. Saturated
          stars, blends and approximate difference imaging are flagged wherever they matter. <Link href="/about">Read the limitations</Link>. ASTRA is an independent project, not affiliated with or
          endorsed by NASA.
        </p>
      </section>
    </main>
  );
}
