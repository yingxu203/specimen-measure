"""Rotate a specimen crop to a standard orientation, for easy visual
comparison across many photos taken at whatever angle the specimen happened
to sit at.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.ndimage import rotate as ndi_rotate, uniform_filter1d
from skimage.morphology import convex_hull_image

from .segmentation import AxesInfo, compute_axes

BACKGROUND_FILL = 25  # dark gray, close to the true dark background color

OrientMode = Literal["apex_down", "vertical", "horizontal"]


@dataclass
class RotatedCrop:
    image: np.ndarray
    mask: np.ndarray
    axes: AxesInfo  # recomputed in the rotated+cropped frame, ready to draw
    flipped: bool  # whether the apex/base flip was applied


def _rotation_degrees(orientation_rad: float, target_deg: float) -> float:
    """Degrees to rotate (via scipy.ndimage.rotate, axes=(0,1)) so a shape
    with this skimage `orientation` ends up at `target_deg` (0 = vertical
    major axis, 90 = horizontal).

    Empirically, `ndi_rotate(angle=X)` shifts the measured orientation by
    +X, so landing on the target just needs the difference between where we
    are and the target.
    """
    return target_deg - math.degrees(orientation_rad)


def _core_body_width_row(
    mask: np.ndarray,
    drop_frac: float = 0.93,
    smooth_size: int = 5,
    search_frac: float = 0.75,
    near_window: int = 15,
) -> tuple[int, float, float]:
    """Find the row that best represents the main body's width, excluding
    a floppy side appendage (a heart's auricle) that can inflate the width
    at some rows but not others.

    Ground-truthed against hand-annotated reference images: a naive
    full-mask bounding-box width consistently overshot manual width
    measurements by 4-18%, always in the same direction, because the
    auricle sticks out sideways near the base and widens exactly the rows
    it occupies. The width profile across rows rises to a peak (the
    auricle-inclusive width) and then drops sharply once the appendage
    ends -- the row just past that drop is the main body's own widest
    point, matching manual annotations within ~1-8% (only one 8-image test
    case, an unusually large auricle, was as far off as 12%).

    Returns (row_index, x_left, x_right) using a real row's own boundary
    (picked as whichever nearby row's raw width is closest to the smoothed
    profile value at the detected transition, so the returned coordinates
    are genuine pixels, not a smoothed/interpolated position).
    """
    rows = np.nonzero(np.any(mask, axis=1))[0]
    r0, r1 = int(rows[0]), int(rows[-1])
    h = r1 - r0

    lefts = np.zeros(h + 1)
    rights = np.zeros(h + 1)
    widths = np.zeros(h + 1)
    for i, y in enumerate(range(r0, r1 + 1)):
        cols = np.nonzero(mask[y, :])[0]
        if len(cols):
            lefts[i], rights[i] = cols[0], cols[-1]
            widths[i] = cols[-1] - cols[0]

    smooth = uniform_filter1d(widths, size=smooth_size)
    search_hi = max(int(h * search_frac), 1)
    idx_peak = int(np.argmax(smooth[:search_hi]))
    peak_val = smooth[idx_peak]

    idx_transition = idx_peak
    for i in range(idx_peak, len(smooth)):
        if smooth[i] < peak_val * drop_frac:
            idx_transition = i
            break
    target_val = smooth[idx_transition]

    lo = max(0, idx_transition - near_window)
    hi = min(len(widths), idx_transition + near_window + 1)
    local_idx = lo + int(np.argmin(np.abs(widths[lo:hi] - target_val)))

    return r0 + local_idx, float(lefts[local_idx]), float(rights[local_idx])


def axis_aligned_extent(mask: np.ndarray, exclude_appendage: bool = False) -> AxesInfo:
    """Measure a mask's straight vertical/horizontal extent (an axis-aligned
    bounding box), meant to be called *after* rotating the mask to a
    standard orientation.

    `compute_axes` connects the two most-extreme pixels found by projecting
    onto the principal-axis directions -- exactly correct as a caliper
    measurement, but for an asymmetric shape those two pixels are often not
    on the same vertical/horizontal line, so the drawn line visibly tilts
    even after rotating the shape "straight". A straight height/width
    measurement is more forgiving of small rotation-angle imperfections and
    matches how someone would actually measure a specimen with a ruler held
    straight after orienting it: total height, total width.

    `exclude_appendage` (heart-specific -- pass only when orient_mode is
    "apex_down") swaps the naive full-mask width for `_core_body_width_row`,
    since ground-truth annotation showed the naive width consistently
    overshoots by including a heart's auricle. Height/length is unaffected:
    it already matched manual annotations well without correction.
    """
    rows = np.nonzero(np.any(mask, axis=1))[0]
    cols = np.nonzero(np.any(mask, axis=0))[0]
    r0, r1 = float(rows[0]), float(rows[-1])
    cx = (cols[0] + cols[-1]) / 2
    cy = (r0 + r1) / 2

    if exclude_appendage:
        y_row, c0, c1 = _core_body_width_row(mask)
        width_y = float(y_row)
    else:
        c0, c1 = float(cols[0]), float(cols[-1])
        width_y = cy

    return AxesInfo(
        centroid_xy=(cx, cy),
        orientation_rad=0.0,
        major_endpoints=((cx, r0), (cx, r1)),        # vertical line
        minor_endpoints=((c0, width_y), (c1, width_y)),  # horizontal line
        major_axis_length_px=r1 - r0,
        minor_axis_length_px=c1 - c0,
    )


def _base_end_is_at_top(mask: np.ndarray) -> bool:
    """Heuristic for which end of a *vertically-oriented* mask is the "base"
    (e.g. a heart's atria/auricles) versus the "apex".

    A heart's ventricle/apex end is smooth and convex (it tapers evenly to a
    rounded or pointed tip), while the base end has the atria and great
    vessels attached, which show up as concave notches in the silhouette --
    the round ventricle body itself can be just as wide near either end, so
    comparing raw width isn't reliable, but comparing how much each half's
    outline deviates from its own convex hull (its "concavity deficit") is:
    whichever half has more hull-but-not-mask area is the notched base.
    Returns True if the top half has more concavity (i.e. the base is
    already at top, no flip needed).
    """
    hull = convex_hull_image(mask)
    deficit = hull & ~mask

    rows_with_content = np.nonzero(np.any(mask, axis=1))[0]
    r0, r1 = int(rows_with_content[0]), int(rows_with_content[-1])
    mid = (r0 + r1) // 2

    top_deficit = deficit[r0:mid, :].sum()
    bottom_deficit = deficit[mid:r1 + 1, :].sum()
    return top_deficit >= bottom_deficit


def rotate_for_display(
    specimen_img: np.ndarray,
    specimen_mask: np.ndarray,
    orient_mode: OrientMode = "apex_down",
    margin: int = 40,
    manual_flip: bool = False,
) -> RotatedCrop:
    """Rotate+crop a specimen for display.

    - "apex_down": long axis vertical, then flipped if needed so the wider/
      notched end (a heart's base/atria) ends up on top and the tapering end
      (apex) on the bottom. Only meaningful for a heart-like elongated shape
      with a genuinely asymmetric base vs. apex.
    - "vertical": long axis vertical, no flip (use for organs/tumors with no
      consistent "this end goes on top" convention).
    - "horizontal": long axis horizontal, no flip.

    `manual_flip` XORs with whatever the automatic orientation decides --
    the automatic base/apex call is a heuristic and won't always be right
    (torn specimens, unusual shapes), so this gives a one-flag override
    (e.g. a UI checkbox) to correct it without needing to reproduce the
    whole rotation from scratch.
    """
    axes = compute_axes(specimen_mask)
    target_deg = 90.0 if orient_mode == "horizontal" else 0.0
    rot_deg = _rotation_degrees(axes.orientation_rad, target_deg)

    rotated_img = ndi_rotate(
        specimen_img.astype(float), angle=rot_deg, axes=(0, 1), reshape=True,
        order=1, mode="constant", cval=BACKGROUND_FILL,
    )
    rotated_img = np.clip(rotated_img, 0, 255).astype(np.uint8)

    rotated_mask = ndi_rotate(
        specimen_mask.astype(float), angle=rot_deg, axes=(0, 1), reshape=True,
        order=0, mode="constant", cval=0.0,
    ) > 0.5

    rows = np.any(rotated_mask, axis=1)
    cols = np.any(rotated_mask, axis=0)
    r0, r1 = np.nonzero(rows)[0][[0, -1]]
    c0, c1 = np.nonzero(cols)[0][[0, -1]]

    h, w = rotated_mask.shape
    r0 = max(r0 - margin, 0)
    r1 = min(r1 + margin, h - 1)
    c0 = max(c0 - margin, 0)
    c1 = min(c1 + margin, w - 1)

    cropped_img = rotated_img[r0:r1 + 1, c0:c1 + 1]
    cropped_mask = rotated_mask[r0:r1 + 1, c0:c1 + 1]

    want_flip = orient_mode == "apex_down" and not _base_end_is_at_top(cropped_mask)
    want_flip = want_flip != manual_flip  # XOR
    if want_flip:
        cropped_img = np.flipud(cropped_img)
        cropped_mask = np.flipud(cropped_mask)

    cropped_axes = axis_aligned_extent(cropped_mask, exclude_appendage=(orient_mode == "apex_down"))
    return RotatedCrop(image=cropped_img, mask=cropped_mask, axes=cropped_axes, flipped=want_flip)
