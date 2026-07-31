"""Rotate a specimen crop to a standard orientation, for easy visual
comparison across many photos taken at whatever angle the specimen happened
to sit at.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.ndimage import rotate as ndi_rotate
from skimage.morphology import convex_hull_image

from .segmentation import AxesInfo, compute_axes

BACKGROUND_FILL = 25  # dark gray, close to the true dark background color

OrientMode = Literal["apex_down", "vertical", "horizontal"]

# Below this ratio between the two halves' concavity deficit, the apex/base
# call is a close guess rather than a clear one -- worth flagging for a
# visual check or manual flip. Chosen from a natural gap in the real dataset
# this was validated against: known-correct images mostly ran >=1.5x, with a
# cluster of genuinely ambiguous ones (one confirmed wrong by inspection) at
# 1.14-1.26x.
LOW_CONFIDENCE_ORIENTATION_RATIO = 1.3


@dataclass
class RotatedCrop:
    image: np.ndarray
    mask: np.ndarray
    axes: AxesInfo  # recomputed in the rotated+cropped frame, ready to draw
    flipped: bool  # whether the apex/base flip was applied
    low_confidence_orientation: bool  # apex/base call was a close guess (apex_down only)


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
    search_frac: float = 0.65,
    relative_deficit_thresh: float = 0.03,
    margin_px: int = 5,
) -> tuple[int, float, float]:
    """Find the row that best represents the ventricle-only width, strictly
    excluding the atria/auricle -- not just reducing their influence.

    A first version of this (finding where the row-width profile peaks then
    drops, ground-truthed against hand-annotated reference images) cut the
    average bias from a systematic +4-18% down to near zero, but individual
    images could still be as far off as +12%, and a follow-up review of the
    drawn line showed it could still graze the atria on some images rather
    than staying clearly clear of it -- the request was specifically "must
    not touch atria at all, only ventricle width".

    This instead finds the actual atria/ventricle boundary directly: the
    atria and auricles show up as concave notches in the silhouette (a
    non-trivial gap between the mask and its own convex hull), while the
    ventricle body is smooth and convex. Scanning down from the top (within
    the region a heart's base can plausibly occupy -- `search_frac` of the
    total height, to avoid unrelated small irregularities near the apex
    tip triggering a false match), the last row with a meaningfully
    concave silhouette (hull-deficit more than `relative_deficit_thresh` of
    that row's own width) marks where the atria end. Only rows strictly
    below that (plus a small safety margin) are considered for width, so
    the result cannot include any atria-influenced row at all.

    Re-validated against the same 8 annotated reference images this
    replaced: -3.6% to +1.2%, versus -12% to +12% for the peak-then-drop
    approach.

    Returns (row_index, x_left, x_right) -- real pixel coordinates of the
    row used, both for reporting and for drawing the width line.
    """
    rows = np.nonzero(np.any(mask, axis=1))[0]
    r0, r1 = int(rows[0]), int(rows[-1])
    h = r1 - r0

    hull = convex_hull_image(mask)
    deficit = (hull & ~mask).sum(axis=1)

    lefts = np.zeros(h + 1)
    rights = np.zeros(h + 1)
    widths = np.zeros(h + 1)
    for i, y in enumerate(range(r0, r1 + 1)):
        cols = np.nonzero(mask[y, :])[0]
        if len(cols):
            lefts[i], rights[i] = cols[0], cols[-1]
            widths[i] = cols[-1] - cols[0]

    search_hi = max(int(h * search_frac), 1)
    notch_idx = [
        i for i in range(search_hi)
        if widths[i] > 0 and deficit[r0 + i] > relative_deficit_thresh * widths[i]
    ]
    last_notch = notch_idx[-1] if notch_idx else 0

    start = min(last_notch + margin_px, h)
    ventricle_widths = widths[start:]
    local_idx = start + (int(np.argmax(ventricle_widths)) if len(ventricle_widths) else 0)

    return r0 + local_idx, float(lefts[local_idx]), float(rights[local_idx])


def _best_length_column(mask: np.ndarray) -> tuple[float, float, float]:
    """Find the column whose own contiguous run of mask pixels comes
    closest to the shape's true total height, so the length line can be
    drawn from real, always-present pixels instead of the bounding box's
    center column.

    The bounding box's true top/bottom rows (from `np.any` over all
    columns) don't necessarily occur at the same column -- for an
    asymmetric shape (e.g. an atria lobe reaching further up on one side
    than the shape's overall center), a line drawn at the center column
    can start above or end below where the mask actually has any pixels
    at that column, visibly poking out past the green contour into the
    background. Searching for the tallest single column's own extent
    keeps the line entirely inside real pixels while normally losing well
    under 2% of the true height (validated against several real photos).

    Returns (x, top_row, bottom_row); prefers a fully contiguous column
    (no internal gaps) over a taller one with gaps, for a clean line.
    """
    rows = np.nonzero(np.any(mask, axis=1))[0]
    r0, r1 = int(rows[0]), int(rows[-1])
    cols = np.nonzero(np.any(mask, axis=0))[0]

    best = None  # (has_gap, -span, x, top, bottom)
    for x in cols:
        rows_at_col = np.nonzero(mask[r0:r1 + 1, x])[0]
        if len(rows_at_col) == 0:
            continue
        top, bottom = int(rows_at_col[0]), int(rows_at_col[-1])
        span = bottom - top
        has_gap = (span + 1) != len(rows_at_col)
        key = (has_gap, -span)
        if best is None or key < best[0]:
            best = (key, x, top, bottom)

    _, x, top, bottom = best
    return float(x), float(r0 + top), float(r0 + bottom)


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

    The height (major axis) line uses `_best_length_column` rather than the
    bounding box's center column: the shape's true topmost and bottommost
    rows don't necessarily fall at the same column (e.g. an atria lobe
    reaching further up on one side than the shape's overall center), so a
    line fixed at the center column could start or end at a background
    pixel, visibly poking out past the green contour. Using the tallest
    single column's own extent keeps the line entirely inside real pixels
    while normally losing well under 2% of the true bounding-box height.

    `exclude_appendage` (heart-specific -- pass only when orient_mode is
    "apex_down") swaps the naive full-mask width for `_core_body_width_row`,
    since ground-truth annotation showed the naive width consistently
    overshoots by including a heart's auricle.
    """
    rows = np.nonzero(np.any(mask, axis=1))[0]
    cols = np.nonzero(np.any(mask, axis=0))[0]
    r0, r1 = float(rows[0]), float(rows[-1])
    cx_bbox = (cols[0] + cols[-1]) / 2
    cy = (r0 + r1) / 2

    length_x, length_top, length_bottom = _best_length_column(mask)

    if exclude_appendage:
        y_row, c0, c1 = _core_body_width_row(mask)
        width_y = float(y_row)
    else:
        c0, c1 = float(cols[0]), float(cols[-1])
        width_y = cy

    return AxesInfo(
        centroid_xy=(cx_bbox, cy),
        orientation_rad=0.0,
        major_endpoints=((length_x, length_top), (length_x, length_bottom)),  # vertical line
        minor_endpoints=((c0, width_y), (c1, width_y)),  # horizontal line
        major_axis_length_px=length_bottom - length_top,
        minor_axis_length_px=c1 - c0,
    )


def _base_deficit_split(mask: np.ndarray) -> tuple[float, float]:
    """Concavity ("hull-but-not-mask" area) in the top half vs bottom half
    of a *vertically-oriented* mask -- see `_base_end_is_at_top`."""
    hull = convex_hull_image(mask)
    deficit = hull & ~mask

    rows_with_content = np.nonzero(np.any(mask, axis=1))[0]
    r0, r1 = int(rows_with_content[0]), int(rows_with_content[-1])
    mid = (r0 + r1) // 2

    top_deficit = float(deficit[r0:mid, :].sum())
    bottom_deficit = float(deficit[mid:r1 + 1, :].sum())
    return top_deficit, bottom_deficit


def _base_end_is_at_top(top_deficit: float, bottom_deficit: float) -> bool:
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

    low_confidence_orientation = False
    if orient_mode == "apex_down":
        top_deficit, bottom_deficit = _base_deficit_split(cropped_mask)
        want_flip = not _base_end_is_at_top(top_deficit, bottom_deficit)
        lo, hi = sorted([top_deficit, bottom_deficit])
        low_confidence_orientation = (hi / lo if lo > 0 else float("inf")) < LOW_CONFIDENCE_ORIENTATION_RATIO
    else:
        want_flip = False
    want_flip = want_flip != manual_flip  # XOR
    if want_flip:
        cropped_img = np.flipud(cropped_img)
        cropped_mask = np.flipud(cropped_mask)

    cropped_axes = axis_aligned_extent(cropped_mask, exclude_appendage=(orient_mode == "apex_down"))
    return RotatedCrop(
        image=cropped_img, mask=cropped_mask, axes=cropped_axes, flipped=want_flip,
        low_confidence_orientation=low_confidence_orientation,
    )
