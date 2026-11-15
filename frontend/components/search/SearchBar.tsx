"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { DETECTOR_RANGES, parseCoordinates } from "@/lib/format";
import { TARGETS } from "@/lib/targets";
import { investigateHref, type InvestigateParams } from "@/lib/url";

const FOV_OPTIONS = [1, 2, 3, 4, 6, 8, 10, 12];

/** Pure-numeric text that is clearly meant as coordinates (so a bad one gets a helpful error, not a name lookup). */
function looksNumeric(s: string): boolean {
  const t = s.replace(/−/g, "-");
  return /^[\s\d+\-.,:°′″'"]+$/.test(t) && (t.match(/\d+(?:\.\d+)?/g)?.length ?? 0) >= 2;
}

export default function SearchBar({
  initialQuery = "",
  initialFov = 3,
  initialDetectors,
}: {
  initialQuery?: string;
  initialFov?: number;
  initialDetectors?: number[];
}) {
  const router = useRouter();
  const [q, setQ] = useState(initialQuery);
  const [fov, setFov] = useState(initialFov);
  const [dets, setDets] = useState<number[]>(initialDetectors?.length ? initialDetectors : [1, 2, 3, 4, 5, 6]);
  const [error, setError] = useState<string | null>(null);

  function toggleDet(d: number) {
    setDets((cur) => (cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d].sort()));
  }

  function go(p: Partial<InvestigateParams>) {
    router.push(investigateHref({ fov, dets: dets.length === 6 ? undefined : dets, ...p }));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const text = q.trim();
    if (!text) {
      setError("Enter a target name (e.g. Barnard's Star) or coordinates (e.g. 133.795 -7.245 or 08 55 10.8 -07 14 42).");
      return;
    }
    if (dets.length === 0) {
      setError("Select at least one detector.");
      return;
    }
    const c = parseCoordinates(text);
    if (c) {
      setError(null);
      go({ ra: c.ra, dec: c.dec });
    } else if (looksNumeric(text)) {
      setError("Could not read those coordinates. Use RA 0–360° (or 0–24 h) and Dec −90° to +90°, as decimal degrees or sexagesimal.");
    } else {
      setError(null);
      go({ name: text });
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3" role="search" aria-label="Find a target">
      <div className="flex flex-col gap-2 sm:flex-row">
        <label className="sr-only" htmlFor="astra-q">
          Target name or coordinates
        </label>
        <input
          id="astra-q"
          className="input flex-1"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            if (error) setError(null);
          }}
          placeholder="Target name or coordinates: Barnard's Star · 133.795 -7.245 · 08h55m10.8s -07d14m42s"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "astra-q-err" : undefined}
        />
        <button type="submit" className="btn btn-primary sm:min-w-[130px]" style={{ minHeight: 40 }}>
          Investigate
        </button>
      </div>
      {error && (
        <p id="astra-q-err" role="alert" className="text-sm text-warn">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
        <label className="flex items-center gap-2">
          Field of view
          <select className="input" value={fov} onChange={(e) => setFov(Number(e.target.value))} aria-label="Field of view in arcminutes">
            {FOV_OPTIONS.map((f) => (
              <option key={f} value={f}>
                {f}′ × {f}′
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Detectors to use">
          <span>Detectors</span>
          {[1, 2, 3, 4, 5, 6].map((d) => (
            <button
              key={d}
              type="button"
              className="btn btn-sm"
              aria-pressed={dets.includes(d)}
              title={`D${d}: ${DETECTOR_RANGES[d][0].toFixed(2)}–${DETECTOR_RANGES[d][1].toFixed(2)} µm`}
              onClick={() => toggleDet(d)}
            >
              D{d}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
        <span>Try a library target:</span>
        {TARGETS.map((t) => (
          <button key={t.slug} type="button" className="btn btn-sm" onClick={() => go({ ra: t.ra, dec: t.dec, name: t.name, fov: t.fov_arcmin })}>
            {t.name}
          </button>
        ))}
      </div>
    </form>
  );
}
