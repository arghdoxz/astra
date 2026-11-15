"use client";

/**
 * Decorative sky behind every page. It is an illustration, NOT survey data:
 * procedurally placed stars with black-body-ish colours, a faint Milky Way band,
 * a sky-chart graticule and a "blink comparator" mover that hops between four
 * epochs (a nod to how moving objects are found). Parallax follows the pointer.
 * Static (no animation) when the user prefers reduced motion.
 */

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

type Star = { x: number; y: number; r: number; a: number; c: string; tw: number };

// Rough main-sequence colour ladder (O/B -> M), weighted toward F/G/K like a real field.
const COLORS = ["#a9bfff", "#c4d3ff", "#e9eeff", "#fff8ef", "#fff1dc", "#ffdcae", "#ffc58a"];
const WEIGHTS = [0.04, 0.1, 0.22, 0.24, 0.2, 0.13, 0.07];

function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function pickColor(u: number) {
  let acc = 0;
  for (let i = 0; i < COLORS.length; i++) {
    acc += WEIGHTS[i];
    if (u <= acc) return COLORS[i];
  }
  return COLORS[3];
}

export default function SkyBackdrop() {
  const ref = useRef<HTMLCanvasElement>(null);
  const pathname = usePathname();
  const dim = pathname !== "/";

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let w = 0, h = 0, dpr = 1;
    let far: HTMLCanvasElement | null = null; // stars + band + graticule, pre-rendered
    let near: Star[] = [];
    let raf = 0;
    const pointer = { x: 0, y: 0, tx: 0, ty: 0 };

    // mover state: four epochs along a short track
    let mover = { x0: 0, y0: 0, dx: 0, dy: 0, t0: 0 };
    const MARGIN = 40;

    const newMover = (now: number) => {
      const R = Math.random;
      const ang = R() * Math.PI * 2;
      const len = 60 + R() * 70;
      mover = {
        x0: w * (0.15 + R() * 0.7),
        y0: h * (0.12 + R() * 0.6),
        dx: (Math.cos(ang) * len) / 3,
        dy: (Math.sin(ang) * len) / 3,
        t0: now,
      };
    };

    const build = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;

      const R = rng(20260402);
      const fw = w + MARGIN * 2, fh = h + MARGIN * 2;
      far = document.createElement("canvas");
      far.width = Math.round(fw * dpr);
      far.height = Math.round(fh * dpr);
      const f = far.getContext("2d")!;
      f.scale(dpr, dpr);

      // Milky Way band: a gently curved diagonal, built from soft blobs + dense faint stars.
      const band = (t: number) => ({ x: t * fw, y: fh * (0.95 - 0.75 * t) + Math.sin(t * 3.1) * fh * 0.06 });
      for (let i = 0; i < 140; i++) {
        const t = R();
        const p = band(t);
        const off = (R() - 0.5) * fh * 0.22;
        const rad = 40 + R() * 120;
        const g = f.createRadialGradient(p.x, p.y + off, 0, p.x, p.y + off, rad);
        g.addColorStop(0, "rgba(170,180,205,0.035)");
        g.addColorStop(1, "rgba(170,180,205,0)");
        f.fillStyle = g;
        f.fillRect(p.x - rad, p.y + off - rad, rad * 2, rad * 2);
      }
      // dust lanes: darken along the band centre
      for (let i = 0; i < 60; i++) {
        const t = R();
        const p = band(t);
        const rad = 30 + R() * 70;
        const g = f.createRadialGradient(p.x, p.y + (R() - 0.5) * 40, 0, p.x, p.y, rad);
        g.addColorStop(0, "rgba(3,5,10,0.35)");
        g.addColorStop(1, "rgba(3,5,10,0)");
        f.fillStyle = g;
        f.fillRect(p.x - rad, p.y - rad, rad * 2, rad * 2);
      }

      // Graticule: lines of constant "RA" converge on an off-screen pole.
      const pole = { x: fw * 0.78, y: -fh * 0.9 };
      f.strokeStyle = "rgba(140,160,200,0.055)";
      f.lineWidth = 1;
      for (let r = fh * 1.0; r < fh * 2.6; r += fh * 0.22) {
        f.beginPath();
        f.arc(pole.x, pole.y, r, 0, Math.PI * 2);
        f.stroke();
      }
      for (let a = Math.PI * 0.15; a < Math.PI * 0.95; a += Math.PI / 18) {
        f.beginPath();
        f.moveTo(pole.x + Math.cos(a) * fh * 1.0, pole.y + Math.sin(a) * fh * 1.0);
        f.lineTo(pole.x + Math.cos(a) * fh * 3, pole.y + Math.sin(a) * fh * 3);
        f.stroke();
      }

      // Field stars: power-law brightness, denser near the band.
      const n = Math.round((fw * fh) / 520);
      for (let i = 0; i < n; i++) {
        let x = R() * fw, y = R() * fh;
        if (R() < 0.45) {
          const p = band(R());
          x = p.x + (R() - 0.5) * 60;
          y = p.y + (R() - 0.5) * fh * 0.25 * R();
        }
        const m = Math.pow(R(), 3.2); // most stars faint
        const r = 0.35 + m * 1.3;
        f.globalAlpha = 0.25 + m * 0.75;
        f.fillStyle = pickColor(R());
        f.beginPath();
        f.arc(x, y, r, 0, Math.PI * 2);
        f.fill();
      }
      f.globalAlpha = 1;

      // A handful of bright stars with faint diffraction spikes.
      for (let i = 0; i < Math.max(6, Math.round((fw * fh) / 160000)); i++) {
        const x = R() * fw, y = R() * fh, c = pickColor(R());
        const g = f.createRadialGradient(x, y, 0, x, y, 9);
        g.addColorStop(0, c);
        g.addColorStop(0.25, "rgba(255,255,255,0.25)");
        g.addColorStop(1, "rgba(255,255,255,0)");
        f.fillStyle = g;
        f.fillRect(x - 9, y - 9, 18, 18);
        f.strokeStyle = "rgba(220,230,255,0.18)";
        f.beginPath();
        f.moveTo(x - 14, y); f.lineTo(x + 14, y);
        f.moveTo(x, y - 14); f.lineTo(x, y + 14);
        f.stroke();
      }

      // Near layer: fewer, slightly brighter stars that twinkle and parallax more.
      const R2 = rng(77);
      near = Array.from({ length: Math.round((w * h) / 9000) }, () => ({
        x: R2() * (w + MARGIN * 2) - MARGIN,
        y: R2() * (h + MARGIN * 2) - MARGIN,
        r: 0.6 + R2() * 0.9,
        a: 0.35 + R2() * 0.5,
        c: pickColor(R2()),
        tw: R2() * Math.PI * 2,
      }));
      newMover(performance.now());
    };

    const draw = (now: number) => {
      pointer.x += (pointer.tx - pointer.x) * 0.05;
      pointer.y += (pointer.ty - pointer.y) * 0.05;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = "#04060b";
      ctx.fillRect(0, 0, w, h);
      if (far) ctx.drawImage(far, -MARGIN - pointer.x * 8, -MARGIN - pointer.y * 8, w + MARGIN * 2, h + MARGIN * 2);

      for (const s of near) {
        const tw = reduce ? 1 : 0.7 + 0.3 * Math.sin(now / 900 + s.tw);
        ctx.globalAlpha = s.a * tw;
        ctx.fillStyle = s.c;
        ctx.beginPath();
        ctx.arc(s.x - pointer.x * 20, s.y - pointer.y * 20, s.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      // blink-comparator mover: 4 epochs, 700 ms each, then fade and relocate
      if (!reduce) {
        const el = now - mover.t0;
        const step = Math.floor(el / 700);
        if (step > 7) newMover(now);
        const k = Math.min(step, 3);
        const ox = -pointer.x * 14, oy = -pointer.y * 14;
        const fade = step > 4 ? Math.max(0, 1 - (el - 5 * 700) / 2100) : 1;
        ctx.strokeStyle = `rgba(255,181,71,${0.35 * fade})`;
        ctx.setLineDash([3, 5]);
        ctx.beginPath();
        ctx.moveTo(mover.x0 + ox, mover.y0 + oy);
        ctx.lineTo(mover.x0 + mover.dx * 3 + ox, mover.y0 + mover.dy * 3 + oy);
        ctx.stroke();
        ctx.setLineDash([]);
        for (let i = 0; i <= k; i++) {
          const x = mover.x0 + mover.dx * i + ox, y = mover.y0 + mover.dy * i + oy;
          const cur = i === k && step <= 4;
          ctx.fillStyle = `rgba(255,190,110,${(cur ? 0.95 : 0.25) * fade})`;
          ctx.beginPath();
          ctx.arc(x, y, cur ? 1.8 : 1.2, 0, Math.PI * 2);
          ctx.fill();
          if (cur) {
            // reticle brackets
            ctx.strokeStyle = `rgba(255,181,71,${0.7 * fade})`;
            const q = 9, l = 4;
            ctx.beginPath();
            for (const [sx, sy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
              ctx.moveTo(x + sx * q, y + sy * (q - l));
              ctx.lineTo(x + sx * q, y + sy * q);
              ctx.lineTo(x + sx * (q - l), y + sy * q);
            }
            ctx.stroke();
          }
        }
      }
      if (!reduce) raf = requestAnimationFrame(draw);
    };

    const onMove = (e: PointerEvent) => {
      pointer.tx = e.clientX / Math.max(w, 1) - 0.5;
      pointer.ty = e.clientY / Math.max(h, 1) - 0.5;
    };
    const onResize = () => {
      build();
      if (reduce) draw(performance.now());
    };
    const onVis = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden && !reduce) raf = requestAnimationFrame(draw);
    };

    build();
    if (reduce) draw(performance.now());
    else raf = requestAnimationFrame(draw);
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("resize", onResize);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("resize", onResize);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  if (pathname === "/embed") return null;
  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 -z-10 transition-opacity duration-700"
      style={{ opacity: dim ? 0.55 : 1 }}
    />
  );
}
