import pytest

from heart_measure.calibration import calibrate
from heart_measure.segmentation import segment_heart
from .synthetic import make_synthetic_photo


def test_segment_heart_recovers_known_axes():
    img = make_synthetic_photo(heart_major_px=220.0, heart_minor_px=160.0)
    gray = img[:, :, :3].mean(axis=2)
    cal = calibrate(gray)
    region = segment_heart(img, cal.ruler_side, cal.ruler_edge_px)

    assert region.major_axis_length_px == pytest.approx(220.0, rel=0.1)
    assert region.minor_axis_length_px == pytest.approx(160.0, rel=0.1)
    assert not region.touches_frame_edge
