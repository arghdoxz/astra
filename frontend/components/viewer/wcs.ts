import type { Grid } from "@/lib/types";

const D2R = Math.PI / 180;
const ARCSEC = 206264.80624709636; // arcsec per radian

/**
 * TAN projection helpers for the shared investigation grid (north up, east left).
 * Grid pixels are 0-based FITS/numpy orientation: array[y, x], y increases north,
 * x increases west. `crpix` in the contract is 1-based, so the reference pixel is crpix-1.
 * For canvas drawing use canvasY = height - 1 - y.
 */
export function skyToGrid(grid: Grid, ra: number, dec: number): { x: number; y: number } {
  const a0 = grid.crval[0] * D2R;
  const d0 = grid.crval[1] * D2R;
  const a = ra * D2R;
  const d = dec * D2R;
  const dA = a - a0;
  const cosc = Math.sin(d0) * Math.sin(d) + Math.cos(d0) * Math.cos(d) * Math.cos(dA);
  const xi = ((Math.cos(d) * Math.sin(dA)) / cosc) * ARCSEC; // arcsec, toward east
  const eta = ((Math.cos(d0) * Math.sin(d) - Math.sin(d0) * Math.cos(d) * Math.cos(dA)) / cosc) * ARCSEC; // toward north
  return {
    x: grid.crpix[0] - 1 - xi / grid.cdelt_arcsec, // east is left
    y: grid.crpix[1] - 1 + eta / grid.cdelt_arcsec,
  };
}

export function gridToSky(grid: Grid, x: number, y: number): { ra: number; dec: number } {
  const xi = (-(x - (grid.crpix[0] - 1)) * grid.cdelt_arcsec) / ARCSEC;
  const eta = ((y - (grid.crpix[1] - 1)) * grid.cdelt_arcsec) / ARCSEC;
  const a0 = grid.crval[0] * D2R;
  const d0 = grid.crval[1] * D2R;
  const rho = Math.hypot(xi, eta);
  if (rho === 0) return { ra: grid.crval[0], dec: grid.crval[1] };
  const c = Math.atan(rho);
  const dec = Math.asin(Math.cos(c) * Math.sin(d0) + (eta * Math.sin(c) * Math.cos(d0)) / rho);
  const ra = a0 + Math.atan2(xi * Math.sin(c), rho * Math.cos(d0) * Math.cos(c) - eta * Math.sin(d0) * Math.sin(c));
  return { ra: (((ra / D2R) % 360) + 360) % 360, dec: dec / D2R };
}
