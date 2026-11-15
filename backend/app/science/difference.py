"""Difference imaging of two registered stacks (SCIENCE_REFERENCE §2.7).

Two honestly-labelled methods:
  * ``simple``      D = S_b - S_a,  Z = D / sqrt(V_a + V_b)
  * ``psf_matched`` the sharper stack is convolved with a Gaussian of sigma_k = sqrt(sigma_broad^2 - sigma_sharp^2)
                    (pixels); its variance is convolved with the squared kernel (V' = V (*) k^2, k unit-sum).
This is a Gaussian approximation; NOT ZOGY or Alard-Lupton. The real SPHEREx PSF is under-sampled and
non-Gaussian, and convolution correlates neighbouring pixels (not propagated into Z).
"""
from __future__ import annotations

import numpy as np
from astropy.convolution import convolve

from ..core_types import DiffResult, Stack

FWHM_TO_SIGMA = 1.0 / 2.3548200450309493
SCALE_TOLERANCE = 0.05      # apply flux scaling only if |ratio - 1| exceeds this
SCALE_MIN_PIXELS = 10       # ... and at least this many pixels went into the median
SCALE_MIN_SNR = 5.0         # reference pixels must have S_a/sqrt(V_a) >= this (noise-only pixels give garbage ratios)
SCALE_PLAUSIBLE = (0.5, 2.0)  # a measured ratio outside this is recorded but never applied
MIN_KERNEL_SIGMA_PX = 0.1   # below this the matching kernel is skipped
NOTE_GAUSSIAN = "Gaussian approximation; not ZOGY"


def _gaussian_kernel(sigma: float) -> np.ndarray:
    r = max(int(np.ceil(4.0 * sigma)), 1)
    ax = np.arange(-r, r + 1, dtype=np.float64)
    k1 = np.exp(-0.5 * (ax / sigma) ** 2)
    k = np.outer(k1, k1)
    return k / k.sum()


def _convolve_stack(S: np.ndarray, V: np.ndarray, sigma: float) -> tuple[np.ndarray, np.ndarray]:
    """Convolve S with unit-sum Gaussian k and V with k^2 (variance of the k-weighted sum). NaN preserved.

    NaN pixels are interpolated over by astropy (kernel renormalised over valid neighbours) and restored
    afterwards (preserve_nan=True). For V the k^2 kernel is renormalised to unit sum for that purpose and the
    result is multiplied back by sum(k^2), which is identical to V (*) k^2 away from NaNs.
    """
    k = _gaussian_kernel(sigma)
    k2 = k * k
    s2 = float(k2.sum())
    S2 = convolve(S, k, boundary="extend", nan_treatment="interpolate", preserve_nan=True,
                  normalize_kernel=True)
    V2 = convolve(V, k2 / s2, boundary="extend", nan_treatment="interpolate", preserve_nan=True,
                  normalize_kernel=True) * s2
    return S2, V2


def zmap(a: Stack, b: Stack, method: str = "simple",
         fwhm_a_px: float | None = None, fwhm_b_px: float | None = None) -> DiffResult:
    """Difference b - a and its significance map.

    Masks are OR-combined (Stack.mask plus non-finite S/V); masked pixels are NaN in D and Z.
    Flux-scale check: median of S_b/S_a over pixels valid in both, S_a > its 90th percentile (and > 0), and
    Z-safe (V_a + V_b > 0). ``flux_scale_measured`` is always recorded when any such pixel exists; the scale is
    applied (b divided by the ratio, V_b divided by ratio^2; ``flux_scale`` = that ratio) only if
    |ratio - 1| > 0.05, at least 10 pixels contributed, and 0.5 < ratio < 2. Reference pixels additionally need
    S_a/sqrt(V_a) >= 5 (deviation from the bare spec: noise-only pixels make the ratio meaningless).
    ``flux_scale`` is 1.0 when not applied.
    ``fwhm_*_px`` are the per-stack PSF FWHM in grid pixels (used only by ``psf_matched``).
    """
    if method not in ("simple", "psf_matched"):
        raise ValueError(f"unknown method {method!r}")
    Sa = np.asarray(a.S, dtype=np.float64).copy()
    Va = np.asarray(a.V, dtype=np.float64).copy()
    Sb = np.asarray(b.S, dtype=np.float64).copy()
    Vb = np.asarray(b.V, dtype=np.float64).copy()
    if Sa.shape != Sb.shape:
        raise ValueError("stacks must share one grid")
    bad_a = np.asarray(a.mask, dtype=bool) | ~np.isfinite(Sa) | ~np.isfinite(Va)
    bad_b = np.asarray(b.mask, dtype=bool) | ~np.isfinite(Sb) | ~np.isfinite(Vb)
    Sa[bad_a] = np.nan
    Va[bad_a] = np.nan
    Sb[bad_b] = np.nan
    Vb[bad_b] = np.nan

    notes: list[str] = []
    kernel_sigma: float | None = None
    used_method = method

    if method == "psf_matched":
        if not (fwhm_a_px and fwhm_b_px and fwhm_a_px > 0 and fwhm_b_px > 0):
            used_method = "simple"
            notes.append("psf_matched requested but FWHM missing; fell back to simple subtraction")
        else:
            sa = float(fwhm_a_px) * FWHM_TO_SIGMA
            sb = float(fwhm_b_px) * FWHM_TO_SIGMA
            sharp_is_a = sa <= sb
            s_sharp, s_broad = (sa, sb) if sharp_is_a else (sb, sa)
            kernel_sigma = float(np.sqrt(max(s_broad ** 2 - s_sharp ** 2, 0.0)))
            if kernel_sigma < MIN_KERNEL_SIGMA_PX:
                notes.append(f"PSF widths match (kernel sigma {kernel_sigma:.2f} px < {MIN_KERNEL_SIGMA_PX} px); "
                             "no convolution applied")
            else:
                if sharp_is_a:
                    Sa, Va = _convolve_stack(Sa, Va, kernel_sigma)
                else:
                    Sb, Vb = _convolve_stack(Sb, Vb, kernel_sigma)
                notes.append(f"convolved sharper stack ({'a' if sharp_is_a else 'b'}) with Gaussian "
                             f"sigma_k={kernel_sigma:.2f} px")

    # --- flux-scale check (on the matched stacks; unit-sum convolution conserves flux) ---
    valid = np.isfinite(Sa) & np.isfinite(Sb) & np.isfinite(Va) & np.isfinite(Vb) & ((Va + Vb) > 0)
    measured: float | None = None
    applied = 1.0
    if valid.any():
        thr = np.percentile(Sa[valid], 90.0)
        with np.errstate(invalid="ignore", divide="ignore"):
            snr_a = Sa / np.sqrt(Va)
        sel = valid & (Sa > thr) & (Sa > 0) & (snr_a >= SCALE_MIN_SNR)
        n_sel = int(sel.sum())
        if n_sel >= 1:
            measured = float(np.median(Sb[sel] / Sa[sel]))
            if n_sel < SCALE_MIN_PIXELS or not np.isfinite(measured):
                notes.append(f"flux-scale check had only {n_sel} usable pixels; not applied")
            elif abs(measured - 1.0) <= SCALE_TOLERANCE:
                notes.append(f"flux scale {measured:.3f} within 5% of unity; not applied")
            elif not (SCALE_PLAUSIBLE[0] < measured < SCALE_PLAUSIBLE[1]):
                notes.append(f"flux scale {measured:.3f} implausible (sources moved or changed?); not applied")
            else:
                applied = measured
                Sb = Sb / applied
                Vb = Vb / applied ** 2
                notes.append(f"flux scale {measured:.3f} (b/a over {n_sel} bright common pixels) applied: "
                             "b divided by it")

    D = Sb - Sa
    den = Va + Vb
    with np.errstate(invalid="ignore", divide="ignore"):
        Z = np.where(den > 0, D / np.sqrt(np.where(den > 0, den, np.nan)), np.nan)
    bad = ~np.isfinite(D) | ~np.isfinite(Z)
    D = np.where(bad, np.nan, D)
    Z = np.where(bad, np.nan, Z)

    notes.append(NOTE_GAUSSIAN if used_method == "psf_matched" else "simple variance-weighted subtraction; not ZOGY")
    return DiffResult(D=D.astype(np.float32), Z=Z.astype(np.float32), method=used_method,
                      flux_scale=float(applied), flux_scale_measured=measured,
                      kernel_sigma_px=kernel_sigma, note="; ".join(notes))
