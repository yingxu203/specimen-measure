import numpy as np
import pytest
from skimage.draw import ellipse

from specimen_measure.calibration import calibrate
from specimen_measure.rotate import axis_aligned_extent, rotate_for_display
from specimen_measure.segmentation import segment_heart
from .synthetic import make_synthetic_photo


def _crop_for(orient_mode: str, **photo_kwargs):
    img = make_synthetic_photo(**photo_kwargs)
    gray = img[:, :, :3].mean(axis=2)
    cal = calibrate(gray)
    region = segment_heart(img, cal.ruler_side, cal.ruler_edge_px)
    specimen_img = img[:, :cal.ruler_edge_px]
    specimen_mask = region.mask[:, :cal.ruler_edge_px]
    return rotate_for_display(specimen_img, specimen_mask, orient_mode=orient_mode), cal


def test_axis_aligned_extent_matches_known_size_after_rotation():
    crop, cal = _crop_for("vertical", heart_major_px=220.0, heart_minor_px=160.0)
    assert crop.axes.major_axis_length_px == pytest.approx(220.0, rel=0.1)
    assert crop.axes.minor_axis_length_px == pytest.approx(160.0, rel=0.1)


def test_axis_endpoints_are_axis_aligned():
    """The drawn length line should be perfectly vertical (constant x) and
    the width line perfectly horizontal (constant y) -- that's the whole
    point of measuring a straight bounding-box extent post-rotation instead
    of a caliper line between two arbitrary extreme pixels."""
    crop, _ = _crop_for("vertical", heart_major_px=220.0, heart_minor_px=160.0)
    (x1, _y1), (x2, _y2) = crop.axes.major_endpoints
    assert x1 == pytest.approx(x2, abs=1e-6)
    (_x3, y3), (_x4, y4) = crop.axes.minor_endpoints
    assert y3 == pytest.approx(y4, abs=1e-6)


def _mask_with_appendage(body_width=200, body_height=400, appendage_extra=150):
    """A vertical oval "body" with a smaller round lobe attached near the
    top and bulging sideways past the body's own edge -- like a heart's
    auricle. Uses a second ellipse (not a hard-edged rectangle) so the
    width profile rises and falls gradually, matching a real auricle's soft
    silhouette instead of a synthetic step function."""
    h, w = body_height + 100, body_width + appendage_extra + 100
    mask = np.zeros((h, w), dtype=bool)
    cy, cx = h // 2, (body_width + 50) // 2 + 25
    rr, cc = ellipse(cy, cx, body_height // 2, body_width // 2, shape=mask.shape)
    mask[rr, cc] = True
    # appendage: a round lobe overlapping the body's upper-right, bulging
    # `appendage_extra` px past the body's own right edge at its center.
    lobe_cy = cy - body_height // 2 + 40
    lobe_cx = cx + body_width // 4
    rr2, cc2 = ellipse(lobe_cy, lobe_cx, 45, appendage_extra + body_width // 4, shape=mask.shape)
    mask[rr2, cc2] = True
    return mask


def test_core_body_width_excludes_appendage():
    """Precise agreement with the body's true width is checked against real
    annotated photos (see rotate.py's docstrings for the ground-truth
    numbers) -- a synthetic shape can't easily reproduce a real auricle's
    exact profile. This just locks in the qualitative behavior: excluding
    the appendage should measure meaningfully narrower than the naive
    bounding box, not leave it unchanged."""
    body_width = 200
    mask = _mask_with_appendage(body_width=body_width, body_height=400, appendage_extra=150)

    naive = axis_aligned_extent(mask, exclude_appendage=False)
    corrected = axis_aligned_extent(mask, exclude_appendage=True)

    assert naive.minor_axis_length_px > body_width * 1.5
    assert corrected.minor_axis_length_px < naive.minor_axis_length_px * 0.95


def test_manual_flip_inverts_orientation():
    crop_a, _ = _crop_for("apex_down", heart_major_px=220.0, heart_minor_px=160.0)
    img = make_synthetic_photo(heart_major_px=220.0, heart_minor_px=160.0)
    gray = img[:, :, :3].mean(axis=2)
    cal = calibrate(gray)
    region = segment_heart(img, cal.ruler_side, cal.ruler_edge_px)
    specimen_img = img[:, :cal.ruler_edge_px]
    specimen_mask = region.mask[:, :cal.ruler_edge_px]
    crop_b = rotate_for_display(specimen_img, specimen_mask, orient_mode="apex_down", manual_flip=True)
    assert crop_b.flipped != crop_a.flipped
