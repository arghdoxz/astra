import Link from "next/link";
import { formatDec, formatRA } from "@/lib/format";
import { targetHref, type LibraryTarget } from "@/lib/targets";
import { investigateHref } from "@/lib/url";

export default function TargetCard({ target, detailed = false }: { target: LibraryTarget; detailed?: boolean }) {
  return (
    <article
      className={`card flex flex-col gap-4 p-5 transition-colors duration-150 hover:border-fg ${
        detailed ? "md:grid md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] md:gap-8" : ""
      }`}
    >
      <div className="flex flex-col gap-3">
        <header>
          <h2 className="serif text-2xl font-semibold">{target.name}</h2>
          <p className="mono text-sm text-pencil">{target.classification}</p>
        </header>
        <p className="mono border-t border-line pt-2 text-sm text-fg">
          {formatRA(target.ra)} {formatDec(target.dec)}
          <span className="block text-muted">
            {target.ra.toFixed(5)}°, {target.dec >= 0 ? "+" : ""}
            {target.dec.toFixed(5)}° (J2000)
          </span>
        </p>
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
      </div>
      <div className="flex max-w-[62ch] flex-col gap-3">
        <p className="text-base text-fg">{target.background}</p>
        {detailed && <p className="border-t border-line pt-3 text-base text-muted">{target.scenario}</p>}
        {detailed && target.challenge && (
          <p className="border-l-2 border-warn pl-3 text-base text-fg">
            <strong className="serif text-warn">Coordinate trap.</strong> {target.challenge.note} ({target.challenge.ra.toFixed(5)}, {target.challenge.dec.toFixed(5)}).{" "}
            <Link href={investigateHref({ ra: target.challenge.ra, dec: target.challenge.dec, fov: 3 })}>Investigate those stale coordinates</Link> to see the difference.
          </p>
        )}
      </div>
    </article>
  );
}
