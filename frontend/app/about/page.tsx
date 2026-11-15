import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "About · ASTRA",
  description: "What ASTRA is, where its data comes from, how it works, and what it cannot do.",
};

const LIMITATIONS = [
  "Centroids and photometry are biased for saturated stars. Flags identify those cases, but no full saturated-PSF fit is done.",
  "Difference imaging is either simple variance-weighted subtraction or a single-Gaussian PSF match; neither is ZOGY / Alard–Lupton.",
  "Variance is reprojected with bilinear interpolation, which correlates neighbouring pixels; stack S/N is therefore slightly optimistic.",
  "ZODI is not subtracted in streaming mode; a per-cutout median and local annulus background are used instead.",
  "WCS registration systematics of about 0.1–0.3″ are not removed (Gaia-relative alignment is a stretch goal).",
  "The wavelength lookup table is approximate to ~1 nm, well below a channel width.",
  "Spectra from one visit mix exposures taken over days to weeks, so fast variables can distort the spectral shape.",
  "QR3 is a quick release. Its calibration matches DR1 per IRSA, but it may be reprocessed later.",
  "Confidence tiers are transparent rules, not calibrated probabilities. ASTRA claims no periods and no discoveries.",
];

const CREDITS = [
  { n: "SPHEREx DR1 and QR3", d: "Spectral images from NASA's SPHEREx mission, served by NASA/IPAC Infrared Science Archive (IRSA). Only DR1 and QR3 are used for time-domain work." },
  { n: "Gaia DR3", d: "European Space Agency (ESA) Gaia mission: positions, proper motions and parallaxes for cross-matching." },
  { n: "SIMBAD", d: "Astronomical database operated at CDS, Strasbourg (via the CDS and Harvard mirrors), for identities and object types." },
  { n: "CatWISE2020", d: "WISE-based catalogue of infrared sources and motions, via NASA/IPAC IRSA." },
  { n: "SkyBoT", d: "IMCCE service for checking whether a moving source is a known solar-system object." },
  { n: "Aladin Lite", d: "CDS interactive sky viewer used for the sky-context panel." },
  { n: "Open-source software", d: "Astropy, photutils, reproject, NumPy and SciPy for the science; FastAPI for the service; Next.js, React and Plotly for the interface." },
];

export default function AboutPage() {
  return (
    <main className="page py-8">
      <article className="prose-astra mx-auto max-w-3xl">
        <h1 className="text-2xl font-semibold">About ASTRA</h1>
        <p className="mt-3">
          ASTRA is a web tool for investigating real infrared observations from NASA&apos;s SPHEREx space telescope over time. Give it a name or a position and it retrieves every public SPHEREx exposure of that
          spot, stacks them into visits roughly six months apart, and shows how the sky changed: which sources moved, which varied, what their 0.75–5 µm spectra look like, and how that compares with what
          catalogues already say. It was built as an entry for NASA Space Apps 2026 (a challenge about finding change in SPHEREx time-domain observations).
        </p>
        <p>
          ASTRA never claims discoveries. Its strongest statement about an unexplained change is &ldquo;needs human review&rdquo;, and its confidence levels are transparent rules, not probabilities.
        </p>

        <h2>Methods in brief</h2>
        <ul>
          <li>Exposures are discovered through the IRSA SIA service and cut out around the target; frames are reprojected onto one shared pixel grid (6.15″ per pixel, north up, east left).</li>
          <li>Exposures are grouped into visits and stacked with variance weighting. Images share one asinh stretch so brightness changes are honest.</li>
          <li>The predicted position of a moving object at each exposure uses its proper motion and parallax. This matters: the WISE 0855 coordinates quoted by the challenge are ~2010 positions and are about 130″ off by 2026.</li>
          <li>Photometry is converted to microjanskys with aperture corrections and SPHEREx&apos;s own flag bits; saturated apertures are reported as lower limits.</li>
          <li>The spectrum is assembled on the fly from the instrument&apos;s linear variable filters, using the wavelength at the target pixel.</li>
          <li>Each evidence item shows its value, threshold and reason, and feeds a rule-based classification. Novelty is tracked separately from reality.</li>
        </ul>

        <h2>Data sources and credits</h2>
        <ul>
          {CREDITS.map((c) => (
            <li key={c.n}>
              <strong className="text-fg">{c.n}.</strong> {c.d}
            </li>
          ))}
        </ul>

        <h2>Limitations</h2>
        <p>Please read these before relying on any number shown in ASTRA.</p>
        <ul>
          {LIMITATIONS.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>

        <h2>Demo snapshots and development placeholders</h2>
        <p>
          When the live service is unavailable, ASTRA can show a precomputed snapshot of real SPHEREx data for library targets that have one, clearly labelled with the date it was generated. During development a
          placeholder bundle with invented numbers may be shown; it carries a red &ldquo;Development placeholder — not real data&rdquo; banner and is never used for results.
        </p>

        <h2>AI disclosure</h2>
        <ul>
          <li>Google Gemini is used to explain the measured evidence in plain language. It is given only the evidence ASTRA computed, and every number in its answer is checked mechanically against that evidence. If the check fails, or the AI is unavailable, a deterministic template explanation is shown instead.</li>
          <li>AI explanations are labelled as such and are not discovery claims.</li>
          <li>This software was written with the help of AI coding assistants.</li>
        </ul>

        <h2>Affiliation</h2>
        <p>
          ASTRA is an independent project. It is <strong className="text-fg">not affiliated with or endorsed by NASA</strong>, the SPHEREx team, IPAC, ESA or CDS.
        </p>
      </article>
    </main>
  );
}
