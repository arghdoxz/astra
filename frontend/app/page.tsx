import Link from "next/link";
import SearchBar from "@/components/search/SearchBar";
import BlinkPlate from "@/components/targets/BlinkPlate";
import { TARGETS, targetHref } from "@/lib/targets";
import { formatDec, formatRA } from "@/lib/format";

/** What ASTRA concluded on each validation target (live runs, Nov 2026; see the About page). */
const FOUND: Record<string, { text: string; tier: string }> = {
  "eps-ind-b": { text: "Motion measured, 0.59σ from the catalogue value", tier: "moderate" },
  "wise-0855": { text: "Motion not measured: blended with a brighter Gaia star 7.2″ away", tier: "low" },
  barnard: { text: "Saturated in 99% of exposures, so motion is not measured", tier: "low" },
  "rw-aur": { text: "Known variable star, matched in SIMBAD", tier: "low" },
  "r-dra": { text: "Saturated; not enough clean data for any claim", tier: "insufficient" },
};

const STEPS: [string, string][] = [
  ["Find the spot.", "A name or coordinates becomes a sky position. If the object moves, its catalogue motion is carried forward to today."],
  ["Pull every plate.", "Every public SPHEREx DR1 and QR3 exposure of that spot comes from NASA/IPAC IRSA, then exposures are grouped into visits about six months apart."],
  ["Blink and measure.", "Visits are stacked, blinked and differenced. ASTRA measures brightness, position and a 0.75 to 5 µm spectrum, and fits the motion."],
  ["Check before believing.", "SPHEREx artifact flags, saturation, blends, Gaia, SIMBAD, CatWISE and known asteroids are checked. Each finding is graded by written rules."],
  ["Explain, then hand over.", "An AI explainer restates the measured evidence and cannot add numbers. People record the verdict. Nothing is called a discovery."],
];

export default function Home() {
  return (
    <main>
      <section className="page grid gap-10 pb-14 pt-10 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] lg:gap-14 lg:pt-14">
        <BlinkPlate />

        <div className="order-first lg:order-none lg:pt-6">
          <h1 className="on-plate serif text-[2.6rem] font-semibold leading-[1.05] sm:text-[3.4rem]">Find what moved.</h1>
          <p className="on-plate mt-5 max-w-[34rem] text-[1.08rem] leading-relaxed">
            In 1930 the Planet X search found Pluto by blinking two photographic plates and looking for the speck that jumped. SPHEREx now photographs the whole sky in 102 infrared colours every
            six months. ASTRA blinks those images for any spot you choose, measures what moved or changed, and shows you the reasons to doubt it.
          </p>
          <div className="card mt-8 p-4 sm:p-5">
            <h2 className="serif mb-3 text-lg font-semibold">Open a plate</h2>
            <SearchBar />
          </div>
          <p className="on-plate mt-4 max-w-[34rem] text-sm text-muted">
            Every image here is real SPHEREx data. The pencil marks are ASTRA&rsquo;s measurements; the dashed line is where the catalogue says the object should be.
          </p>
        </div>
      </section>

      <section className="page pb-14" aria-labelledby="library">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <h2 id="library" className="on-plate serif text-[1.9rem] font-semibold">
            Plate index
          </h2>
          <p className="on-plate text-sm text-muted">
            Five objects where the right answer is already known, so you can see ASTRA get it right and see it refuse. <Link href="/targets">Why these five</Link>
          </p>
        </div>
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[46rem] border-collapse text-left">
            <thead>
              <tr className="border-b border-fg text-sm text-muted">
                <th className="px-4 py-2.5 font-semibold">Plate</th>
                <th className="px-4 py-2.5 font-semibold">Object</th>
                <th className="px-4 py-2.5 font-semibold">Position (J2000)</th>
                <th className="px-4 py-2.5 font-semibold">What ASTRA found</th>
                <th className="px-4 py-2.5 font-semibold">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {TARGETS.map((t, k) => {
                const f = FOUND[t.slug];
                return (
                  <tr key={t.slug} className="border-b border-line last:border-b-0 hover:bg-bg/60">
                    <td className="mono px-4 py-3 align-top text-sm text-muted">A-{String(417 + k).padStart(4, "0")}</td>
                    <td className="px-4 py-3 align-top">
                      <Link href={targetHref(t)} className="serif text-[1.15rem] font-semibold text-fg">
                        {t.name}
                      </Link>
                      <div className="text-sm text-muted">{t.classification}</div>
                    </td>
                    <td className="mono px-4 py-3 align-top text-sm">
                      {formatRA(t.ra)}
                      <br />
                      {formatDec(t.dec)}
                    </td>
                    <td className="px-4 py-3 align-top text-[0.95rem]">{f?.text}</td>
                    <td className={`mono px-4 py-3 align-top text-sm ${f?.tier === "moderate" ? "text-good" : "text-pencil"}`}>{f?.tier}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="page grid gap-10 pb-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]" aria-labelledby="how">
        <div>
          <h2 id="how" className="on-plate serif text-[1.9rem] font-semibold">
            How a plate is read
          </h2>
          <p className="on-plate mt-3 max-w-md text-muted">The same procedure runs for any position on the sky, live, on the public SPHEREx archive.</p>
        </div>
        <ol className="on-plate space-y-5">
          {STEPS.map(([title, body]) => (
            <li key={title} className="border-t border-line pt-4">
              <h3 className="serif text-lg font-semibold">{title}</h3>
              <p className="mt-1">{body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="page pb-6" aria-labelledby="honesty">
        <div className="card px-5 py-6 sm:px-6">
          <h2 id="honesty" className="serif text-[1.5rem] font-semibold">
            What ASTRA will not do
          </h2>
          <p className="mt-2">
            ASTRA never announces discoveries. The strongest thing it can say about an unexplained change is &ldquo;needs human review&rdquo;. Confidence levels are written rules, not
            probabilities. Saturated stars, blends and approximate difference imaging are flagged wherever they matter. <Link href="/about">Read the limitations</Link>.
          </p>
        </div>
      </section>
    </main>
  );
}
