import math

import pytest

from specimen_measure.calibration import calibrate
from specimen_measure.segmentation import compute_axes, segment_heart
from .synthetic import make_synthetic_photo


def test_segment_heart_finds_the_specimen():
    img = make_synthetic_photo(heart_major_px=220.0, heart_minor_px=160.0)
    gray = img[:, :, :3].mean(axis=2)
    cal = calibrate(gray)
    region = segment_heart(img, cal.ruler_side, cal.ruler_edge_px)

    assert region.area_px == pytest.approx(math.pi * 110.0 * 80.0, rel=0.05)
    assert not region.touches_frame_edge


def test_compute_axes_recovers_known_caliper_length():
    img = make_synthetic_photo(heart_major_px=220.0, heart_minor_px=160.0)
    gray = img[:, :, :3].mean(axis=2)
    cal = calibrate(gray)
    region = segment_heart(img, cal.ruler_side, cal.ruler_edge_px)

    axes = compute_axes(region.mask)
    assert axes.major_axis_length_px == pytest.approx(220.0, rel=0.1)
    assert axes.minor_axis_length_px == pytest.approx(160.0, rel=0.1)
