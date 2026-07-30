"""Build a synthetic specimen photo with a known scale and heart size, so the
test suite can check the pipeline's numeric output against ground truth
without needing access to any real (private) specimen photos.
"""
from __future__ import annotations

import numpy as np
from skimage.draw import ellipse


def make_synthetic_photo(
    height: int = 600,
    width: int = 800,
    ruler_width: int = 200,
    px_per_mm: float = 20.0,
    heart_major_px: float = 220.0,
    heart_minor_px: float = 160.0,
    rng_seed: int = 0,
) -> np.ndarray:
    """Returns an HxWx3 uint8 image: dark speckled background, an elliptical
    "heart" blob, and a bright ruler panel on the right edge with tick marks
    spaced `px_per_mm` pixels apart.
    """
    rng = np.random.default_rng(rng_seed)
    img = np.full((height, width, 3), 20, dtype=np.uint8)
    noise = rng.integers(0, 25, size=(height, width), endpoint=False)
    img += noise[:, :, None].astype(np.uint8)

    ruler_left = width - ruler_width
    img[:, ruler_left:, :] = 235

    rr, cc = ellipse(
        height // 2, ruler_left // 2,
        heart_major_px / 2, heart_minor_px / 2,
        shape=img.shape[:2],
    )
    img[rr, cc, 0] = 220
    img[rr, cc, 1] = 150
    img[rr, cc, 2] = 130

    tick_x0 = ruler_left + 2
    tick_x1 = ruler_left + 18
    y = 0.0
    while y < height:
        yi = int(round(y))
        img[max(yi - 1, 0):yi + 1, tick_x0:tick_x1, :] = 40
        y += px_per_mm

    return img
