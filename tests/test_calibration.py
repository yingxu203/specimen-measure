import numpy as np
import pytest

from heart_measure.calibration import CalibrationError, calibrate
from .synthetic import make_synthetic_photo


def test_calibrate_recovers_known_scale():
    img = make_synthetic_photo(px_per_mm=20.0)
    gray = img[:, :, :3].mean(axis=2)
    cal = calibrate(gray)
    assert cal.ruler_side == "right"
    assert cal.n_ticks >= 10
    assert cal.px_per_mm == pytest.approx(20.0, rel=0.05)


def test_calibrate_handles_partial_height_ruler():
    """A ruler that doesn't reach the top of the frame (tilt/crop) shouldn't
    corrupt the tick spacing estimate."""
    img = make_synthetic_photo(height=600, width=800, px_per_mm=15.0)
    # Blank out the top 150 rows of the ruler panel to simulate a cropped/tilted ruler.
    img[:150, 600:, :] = 20
    gray = img[:, :, :3].mean(axis=2)
    cal = calibrate(gray)
    assert cal.px_per_mm == pytest.approx(15.0, rel=0.1)


def test_calibrate_raises_when_no_ruler_present():
    img = np.full((300, 400, 3), 20, dtype=np.uint8)
    gray = img[:, :, :3].mean(axis=2)
    with pytest.raises(CalibrationError):
        calibrate(gray)
