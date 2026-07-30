import pytest

from specimen_measure.calibration import calibrate
from specimen_measure.rotate import rotate_for_display
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
