Created on 7/30/26
@author: yingxu203
"""Detect the ruler panel in a specimen photo and derive a pixels-per-mm scale
from the spacing between its millimeter tick marks.

Assumes the classic photography setup used for these heart specimens: the
sample sits on a dark, matte background and a printed ruler (bright panel with
dark tick marks) is butted up against one edge of the frame, oriented with its
ticks running horizontally (i.e. the ruler's long axis is vertical in the
image).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks


class CalibrationError(RuntimeError):
    """Raised when the ruler or its tick marks cannot be reliably located."""


@dataclass
class Calibration:
    ruler_side: str          # "left" or "right"
    ruler_edge_px: int        # column where the ruler panel begins
    px_per_mm: float
    n_ticks: int
    tick_spacing_std_px: float


def detect_ruler_edge(gray: np.ndarray, side: str = "auto", min_run_frac: float = 0.1) -> tuple[str, int]:
    """Find which side of the frame the ruler is on and the column where it starts.

    Returns (side, edge_px) where edge_px is the column index of the boundary
    between the specimen area and the ruler panel (the ruler occupies columns
    >= edge_px if side == "right", or columns <= edge_px if side == "left").
    """
    h, w = gray.shape
    col_mean = gray.mean(axis=0)
    thresh = col_mean.max() * 0.5
    bright = col_mean > thresh

    def run_from_right() -> int | None:
        run_start = None
        for x in range(w - 1, -1, -1):
            if bright[x]:
                if run_start is None:
                    run_start = x
            elif run_start is not None:
                if run_start - x > w * min_run_frac:
                    return x + 1
                run_start = None
        return None

    def run_from_left() -> int | None:
        run_start = None
        for x in range(w):
            if bright[x]:
                if run_start is None:
                    run_start = x
            elif run_start is not None:
                if x - run_start > w * min_run_frac:
                    return x - 1
                run_start = None
        return None

    if side in ("right", "auto"):
        edge = run_from_right()
        if edge is not None:
            return "right", edge
    if side in ("left", "auto"):
        edge = run_from_left()
        if edge is not None:
            return "left", edge
    raise CalibrationError(
        "Could not find a bright ruler panel touching the left or right edge of the frame."
    )


# Grayscale level (0-255) below which a row is unambiguously background, not
# ruler. The dark specimen backgrounds observed in this dataset run ~40-90;
# even the dimmest ruler tick dips stay well above 130. Kept generous on
# purpose: a real background/ruler split should look nothing like a marginal
# call, so this only fires on a clear case.
_BACKGROUND_MAX_LEVEL = 130.0


def _trim_to_ruler_rows(strip: np.ndarray, margin: int = 3) -> tuple[int, int]:
    """Find the row range within `strip` that is actually the ruler panel.

    The ruler doesn't always span the full frame height -- a slight tilt or a
    rounded/cropped corner can leave a run of genuine dark-background rows
    mixed into the sampled strip, which would otherwise dilute tick contrast
    and bias the fitted spacing. Otsu alone isn't trustworthy here: applied to
    an all-ruler strip it still finds *some* split (e.g. between tick dips and
    the ruler's base color), so any split it finds is only trusted when the
    "low" side is dark enough to be real background and touches an edge of
    the strip (a tilt/crop cuts off one end, it doesn't carve out the middle).
    """
    from skimage.filters import threshold_otsu

    n = len(strip)
    # Smooth heavily first so individual tick dips (a few px wide) don't get
    # mistaken for a background region -- only broad, tens-of-px+ brightness
    # transitions should count as a real ruler/background boundary.
    coarse = uniform_filter1d(strip, size=21)
    if coarse.max() <= coarse.min():
        return 0, n

    thresh = threshold_otsu(coarse)
    bright = coarse > thresh
    if not bright.any() or bright.all():
        return 0, n
    if coarse[~bright].mean() > _BACKGROUND_MAX_LEVEL:
        return 0, n  # "low" side isn't actually dark background -- don't trim

    best_start, best_len, run_start = 0, 0, None
    for i, b in enumerate(np.append(bright, False)):
        if b:
            if run_start is None:
                run_start = i
        elif run_start is not None:
            if i - run_start > best_len:
                best_start, best_len = run_start, i - run_start
            run_start = None

    touches_edge = best_start == 0 or (best_start + best_len) == n
    if not touches_edge:
        return 0, n  # a trustworthy tilt/crop cuts off an end, not the middle

    return best_start + margin, best_start + best_len - margin


def detect_px_per_mm(
    gray: np.ndarray,
    ruler_side: str,
    ruler_edge_px: int,
    strip_offset: tuple[int, int] = (5, 25),
    min_ticks: int = 5,
) -> tuple[float, int, float]:
    """Estimate pixels-per-millimeter from tick spacing on the ruler.

    Samples a narrow vertical strip just inside the ruler's near edge (close
    enough that every mm tick reaches it, but before any printed text/numerals
    would interfere), then finds the regularly-spaced dark tick marks in that
    strip's row-wise brightness profile.
    """
    h, w = gray.shape
    lo, hi = strip_offset
    if ruler_side == "right":
        x0, x1 = ruler_edge_px + lo, min(ruler_edge_px + hi, w - 1)
    else:
        x0, x1 = max(ruler_edge_px - hi, 0), max(ruler_edge_px - lo, 1)
    if x1 <= x0:
        raise CalibrationError("Ruler panel too narrow to sample a tick strip.")

    strip = gray[:, x0:x1].mean(axis=1)
    lo_row, hi_row = _trim_to_ruler_rows(strip)
    if hi_row <= lo_row:
        raise CalibrationError("Ruler panel too short (after excluding non-ruler rows) to find ticks.")

    sub = strip[lo_row:hi_row]
    inv = sub.max() - sub
    inv -= inv.min()
    inv = uniform_filter1d(inv, size=3)

    peaks, _ = find_peaks(inv, distance=5, prominence=max(inv.max() * 0.15, 1e-6))
    if len(peaks) < min_ticks:
        raise CalibrationError(
            f"Only found {len(peaks)} ruler ticks (need >= {min_ticks}); calibration unreliable."
        )
    peaks = peaks + lo_row

    # Robust spacing estimate: least-squares fit of tick position vs tick index,
    # which averages out noise better than a plain median of consecutive diffs.
    idx = np.arange(len(peaks))
    slope, _ = np.polyfit(idx, peaks, 1)
    px_per_mm = abs(slope)

    diffs = np.diff(peaks)
    spacing_std = float(np.std(diffs))
    return float(px_per_mm), len(peaks), spacing_std


def calibrate(gray: np.ndarray, ruler_side: str = "auto", **kwargs) -> Calibration:
    side, edge = detect_ruler_edge(gray, side=ruler_side)
    px_per_mm, n_ticks, spacing_std = detect_px_per_mm(gray, side, edge, **kwargs)
    return Calibration(
        ruler_side=side,
        ruler_edge_px=edge,
        px_per_mm=px_per_mm,
        n_ticks=n_ticks,
        tick_spacing_std_px=spacing_std,
    )
