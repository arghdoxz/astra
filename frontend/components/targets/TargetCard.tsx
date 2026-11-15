import Link from "next/link";
import { formatDec, formatRA } from "@/lib/format";
import { targetHref, type LibraryTarget } from "@/lib/targets";
import { investigateHref } from "@/lib/url";

export default function TargetCard({ target, detailed = false }: { target: LibraryTarget; detailed?: boolean }) {
  return (
    <article className="card frame card-pad flex flex-col gap-3 transition-colors duration-200 hover:border-[#34435f]">
      <header>
        <h3 className="font-[family-name:var(--font-display)] text-xl font-semibold">{target.name}</h3>
        <p className="mono text-xs text-sodium">{target.classification}</p>
      </header>
      <p className="mono text-xs text-muted">
        {formatRA(target.ra)} {formatDec(target.dec)}
        <span className="block opacity-80">
          {target.ra.toFixed(5)}°, {target.dec >= 0 ? "+" : ""}
          {target.dec.toFixed(5)}° (J2000)
        </span>
      </p>
      <p className="text-sm text-[#c5cde0]">{target.background}</p>
      {detailed && <p className="rounded-sm border border-line bg-bg/60 p-3 text-sm text-[#c5cde0]">{target.scenario}</p>}
      {detailed && target.challenge && (
        <p className="rounded-sm border border-warn/40 bg-warn/5 p-3 text-sm text-[#c5cde0]">
          <strong className="text-warn">Coordinate trap.</strong> {target.challenge.note} ({target.challenge.ra.toFixed(5)}, {target.challenge.dec.toFixed(5)}).{" "}
          <Link href={investigateHref({ ra: target.challenge.ra, dec: target.challenge.dec, fov: 3 })}>
            Investigate those stale coordinates
          </Link>{" "}
          to see the difference.
        </p>
      )}
      <ul className="flex flex-wrap gap-1.5" aria-label="Capabilities demonstrated">
        {target.capabilities.map((c) => (
          <li key={c} className="chip chip-cyan">
            {c}
          </li>
        ))}
      </ul>
      <div className="mt-auto pt-1">
        <Link href={targetHref(target)} className="btn btn-primary no-underline hover:no-underline" aria-label={`Investigate ${target.name}`}>
          Investigate
        </Link>
      </div>
    </article>
  );
}
