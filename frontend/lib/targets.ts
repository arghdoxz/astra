import { investigateHref } from "@/lib/url";

export interface LibraryTarget {
  slug: string;
  name: string;
  /** Alternative spellings used for name matching in offline mode. */
  aliases: string[];
  ra: number;
  dec: number;
  classification: string;
  background: string;
  capabilities: string[];
  scenario: string;
  fov_arcmin: number;
  /** Coordinates quoted by the challenge text, if they differ (WISE 0855). */
  challenge?: { ra: number; dec: number; note: string };
}

export const TARGETS: LibraryTarget[] = [
  {
    slug: "barnard",
    name: "Barnard's Star",
    aliases: ["barnard", "barnards star", "barnard's star", "gj 699", "gl 699", "hip 87937"],
    ra: 269.45208,
    dec: 4.69336,
    classification: "M4V red dwarf · fastest proper motion",
    background:
      "The star with the largest known proper motion (about 10.4 arcsec per year), only ~6 light-years away. Over the SPHEREx baseline it drifts by a couple of pixels.",
    capabilities: ["Proper motion", "Parallax", "Saturation flags"],
    scenario:
      "Validation scenario: saturation plus very high proper motion. The star is bright enough to saturate most SPHEREx detectors, so centroids and photometry are flagged as biased or lower limits, and ASTRA leans on agreement between the predicted track and the measurements.",
    fov_arcmin: 3,
  },
  {
    slug: "eps-ind-b",
    name: "Eps Ind B",
    aliases: ["eps ind b", "epsilon indi b", "eps indi b", "epsilon ind b", "eps ind ba", "eps ind bab"],
    ra: 331.04415,
    dec: -56.78284,
    classification: "T1+T6 brown-dwarf binary · high proper motion",
    background:
      "The nearest known brown dwarfs (~11 light-years), orbiting the K-dwarf Eps Indi A. Fast proper motion and a methane-dominated infrared spectrum.",
    capabilities: ["Proper motion", "CH₄ spectrum", "Difference imaging"],
    scenario:
      "Validation scenario: brown-dwarf astrometry. The source is unsaturated and moves several pixels, so it is the cleanest test of the measured proper-motion fit against the catalogue value, and of a methane absorption feature in the on-the-fly spectrum.",
    fov_arcmin: 3,
  },
  {
    slug: "wise-0855",
    name: "WISE 0855-0714",
    aliases: ["wise 0855", "wise 0855-0714", "wise 0855−0714", "wise j085510.83-071442.5", "wise j0855-0714", "wise0855"],
    ra: 133.81891,
    dec: -7.24705,
    classification: "Y-dwarf · coldest known brown dwarf",
    background:
      "A ~285 K object about 7 light-years away with the third-largest proper motion known. Extremely faint: only detectable at the longest SPHEREx wavelengths.",
    capabilities: ["Faint source", "Stacking", "Coordinate propagation"],
    scenario:
      "Validation scenario: faint-source stacking and the coordinate trap. The coordinates quoted by the challenge (about 2010, WISE era) are roughly 130 arcsec from where the object is in 2026. ASTRA propagates its proper motion, so the cutout is centred on the object rather than empty sky. Expect a marginal detection only in D5/D6 visit stacks.",
    fov_arcmin: 3,
    challenge: {
      ra: 133.79513,
      dec: -7.24515,
      note: "Challenge text coordinates (~2010 position): 08h55m10.831s −07°14′42.53″",
    },
  },
  {
    slug: "rw-aur",
    name: "RW Aurigae",
    aliases: ["rw aur", "rw aurigae", "rw aur a"],
    ra: 76.95653,
    dec: 30.40144,
    classification: "T Tauri star · irregular variable",
    background:
      "A young, actively accreting star with deep, irregular dimming episodes caused by dusty material passing in front of it, and a strong infrared excess.",
    capabilities: ["Variability", "Light curve", "Saturation flags"],
    scenario:
      "Validation scenario: variability. Brightness can change between visits, but the star saturates most detectors, so ASTRA reports variability metrics with lower limits and prefers the unsaturated long-wavelength detectors.",
    fov_arcmin: 3,
  },
  {
    slug: "r-dra",
    name: "R Draconis",
    aliases: ["r dra", "r draconis"],
    ra: 248.16761,
    dec: 66.75498,
    classification: "Mira variable · pulsating red giant",
    background:
      "A cool, evolved star that pulsates with a period of roughly 245 days, swinging strongly in infrared brightness. It lies near the ecliptic pole, so SPHEREx observes it often.",
    capabilities: ["Mira variability", "Dense coverage", "Spectra per visit"],
    scenario:
      "Validation scenario: Mira variability plus coverage. Visits about six months apart sample different pulsation phases, so band depths can change between visits. The star is mostly saturated, so results are flag-aware lower limits.",
    fov_arcmin: 3,
  },
];

export function targetHref(t: LibraryTarget, base = "/investigate"): string {
  return investigateHref({ ra: t.ra, dec: t.dec, fov: t.fov_arcmin, name: t.name }, base);
}

export function findTargetByName(q: string): LibraryTarget | null {
  const n = q.trim().toLowerCase().replace(/’/g, "'").replace(/−/g, "-").replace(/\s+/g, " ");
  if (!n) return null;
  for (const t of TARGETS) {
    if (t.slug === n || t.name.toLowerCase() === n || t.aliases.includes(n) || t.aliases.includes(n.replace(/'/g, ""))) return t;
  }
  return null;
}
