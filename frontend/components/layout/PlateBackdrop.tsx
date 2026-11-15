"use client";

/**
 * The page surface is drawn as a photographic sky plate on a light box: a NEGATIVE,
 * so stars are dark specks on pale glass, with the réseau grid that astrographic plates
 * carried for measurement. On the landing page a loupe follows the pointer and shows the
 * same patch as a magnified positive (the dark sky as the eye sees it).
 *
 * It is an illustration, NOT survey data (the footer says so). It sits behind the content,
 * so paper sheets cover it and it never runs under body text at full strength.
 */

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

type Speck = { x: number; y: number; r: number; a: number };

const GLASS = "#e3e6e4";
const INK = "18,20,22";
const GRID = 132; // réseau spacing in CSS px
const LOUPE_R = 92;
const MAG = 2.2;

function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

export default function PlateBackdrop() {
  const ref = useRef<HTMLCanvasElement>(null);
  const pathname = usePathname();
  const landing = pathname === "/";
  const hidden = pathname === "/embed";

  useEffect(() => {
    if (hidden) return;
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const finePointer = window.matchMedia("(pointer: fine)").matches;

    let w = 0, h = 0, dpr = 1;
    let neg: HTMLCanvasElement | null = null; // negative plate, pre-rendered
    let pos: HTMLCanvasElement | null = null; // positive sky, same specks, for the loupe
    let specks: Speck[] = [];
    let raf = 0;
    const pointer = { x: -9999, y: -9999, inside: false };

    const genSpecks = () => {
      const R = rng(0x5eed ^ Math.round(w) ^ (Math.round(h) << 12));
      const n = Math.round((w * h) / 5200);
      specks = [];
      for (let i = 0; i < n; i++) {
        // Power-law brightness: most specks are faint, a few are bold.
        const u = R();
        const bright = Math.pow(u, 6);
        specks.push({ x: R() * w, y: R() * h, r: 0.45 + bright * 3.4, a: 0.1 + Math.min(1, bright * 2.4) * 0.38 });
      }
    };

    const drawPlate = (c: CanvasRenderingContext2D, positive: boolean) => {
      c.fillStyle = positive ? "#05070a" : GLASS;
      c.fillRect(0, 0, w, h);
      if (!positive) {
        // Emulsion is never perfectly even: a few very broad, very faint density variations.
        const R = rng(77);
        for (let i = 0; i < 5; i++) {
          const x = R() * w, y = R() * h, rr = Math.max(w, h) * (0.25 + R() * 0.35);
          const g = c.createRadialGradient(x, y, 0, x, y, rr);
          g.addColorStop(0, `rgba(${INK},0.035)`);
          g.addColorStop(1, `rgba(${INK},0)`);
          c.fillStyle = g;
          c.fillRect(0, 0, w, h);
        }
      }
      for (const s of specks) {
        const col = positive ? `rgba(255,255,255,${Math.min(1, s.a + 0.15)})` : `rgba(${INK},${s.a})`;
        if (s.r > 2) {
          // Bright stars bloom in the emulsion.
          const g = c.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.r * 2.6);
          g.addColorStop(0, positive ? `rgba(255,255,255,${s.a * 0.35})` : `rgba(${INK},${s.a * 0.28})`);
          g.addColorStop(1, positive ? "rgba(255,255,255,0)" : `rgba(${INK},0)`);
          c.fillStyle = g;
          c.beginPath();
          c.arc(s.x, s.y, s.r * 2.6, 0, Math.PI * 2);
          c.fill();
        }
        c.fillStyle = col;
        c.beginPath();
        c.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        c.fill();
      }
      if (!positive) {
        // Réseau: the measuring grid exposed onto astrographic plates.
        c.strokeStyle = `rgba(${INK},0.10)`;
        c.lineWidth = 1;
        c.beginPath();
        for (let x = GRID / 2; x < w; x += GRID) {
          c.moveTo(Math.round(x) + 0.5, 0);
          c.lineTo(Math.round(x) + 0.5, h);
        }
        for (let y = GRID / 2; y < h; y += GRID) {
          c.moveTo(0, Math.round(y) + 0.5);
          c.lineTo(w, Math.round(y) + 0.5);
        }
        c.stroke();
      } else {
        // Through the loupe the eye picks up what the plate barely recorded: many faint stars
        // and a little diffuse glow. These are drawn small because the loupe magnifies them.
        const R = rng(0xfa1e ^ Math.round(w));
        for (let i = 0; i < 4; i++) {
          const x = R() * w, y = R() * h, rr = 140 + R() * 260;
          const g = c.createRadialGradient(x, y, 0, x, y, rr);
          g.addColorStop(0, `rgba(${R() < 0.5 ? "120,140,190" : "190,150,130"},0.22)`);
          g.addColorStop(1, "rgba(0,0,0,0)");
          c.fillStyle = g;
          c.fillRect(x - rr, y - rr, rr * 2, rr * 2);
        }
        const n = Math.round((w * h) / 150);
        for (let i = 0; i < n; i++) {
          const a = 0.35 + Math.pow(R(), 2) * 0.65;
          c.fillStyle = `rgba(${R() < 0.2 ? "255,226,196" : R() < 0.25 ? "200,215,255" : "255,255,255"},${a})`;
          const sz = R() < 0.9 ? 0.8 : 1.4;
          c.fillRect(R() * w, R() * h, sz, sz);
        }
      }
    };

    const build = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      genSpecks();
      const make = (positive: boolean) => {
        const off = document.createElement("canvas");
        off.width = canvas.width;
        off.height = canvas.height;
        const oc = off.getContext("2d");
        if (oc) {
          oc.setTransform(dpr, 0, 0, dpr, 0, 0);
          drawPlate(oc, positive);
        }
        return off;
      };
      neg = make(false);
      pos = landing ? make(true) : null;
    };

    const draw = () => {
      raf = 0;
      if (!neg) return;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(neg, 0, 0);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (!landing) return;

      // Loupe: magnified positive of the patch under the pointer.
      if (pos && pointer.inside && finePointer) {
        const { x, y } = pointer;
        ctx.save();
        ctx.beginPath();
        ctx.arc(x, y, LOUPE_R, 0, Math.PI * 2);
        ctx.clip();
        const sw = ((LOUPE_R * 2) / MAG) * dpr;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.drawImage(pos, x * dpr - sw / 2, y * dpr - sw / 2, sw, sw, (x - LOUPE_R) * dpr, (y - LOUPE_R) * dpr, LOUPE_R * 2 * dpr, LOUPE_R * 2 * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.restore();
        ctx.strokeStyle = "#121416";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(x, y, LOUPE_R, 0, Math.PI * 2);
        ctx.stroke();
        ctx.lineWidth = 1;
        ctx.strokeStyle = "rgba(255,255,255,0.35)";
        ctx.beginPath();
        for (const [ax, ay] of [[0, -1], [0, 1], [-1, 0], [1, 0]]) {
          ctx.moveTo(x + ax * (LOUPE_R - 12), y + ay * (LOUPE_R - 12));
          ctx.lineTo(x + ax * (LOUPE_R - 2), y + ay * (LOUPE_R - 2));
        }
        ctx.stroke();
      }
    };

    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(draw);
    };

    build();
    schedule();

    const onResize = () => {
      build();
      schedule();
    };
    const onMove = (e: PointerEvent) => {
      pointer.x = e.clientX;
      pointer.y = e.clientY;
      pointer.inside = true;
      schedule();
    };
    const onLeave = () => {
      pointer.inside = false;
      schedule();
    };
    window.addEventListener("resize", onResize);
    if (landing && finePointer) {
      window.addEventListener("pointermove", onMove, { passive: true });
      document.documentElement.addEventListener("pointerleave", onLeave);
    }
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onLeave);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [landing, hidden]);

  if (hidden) return null;
  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 -z-10"
      style={{ opacity: landing ? 1 : 0.6 }}
    />
  );
}
