"""Rotate a specimen crop so its long axis is horizontal, for easy visual
comparison across many photos taken at whatever angle the heart happened to
sit at.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import rotate as ndi_rotate

from .segmentation import AxesInfo, compute_axes

BACKGROUND_FILL = 25  # dark gray, close to the true dark background color


@dataclass
class RotatedCrop:
    image: np.ndarray
    mask: np.ndarray
    axes: AxesInfo  # recomputed in the rotated+cropped frame, ready to draw


def _rotation_degrees_for_horizontal(orientation_rad: float) -> float:
    """Degrees to rotate (via scipy.ndimage.rotate, axes=(0,1)) so a shape
    with this skimage `orientation` ends up with its major axis horizontal.

    Empirically, `ndi_rotate(angle=X)` shifts the measured orientation by
    +X (mod the +-90 deg wraparound inherent to a line's orientation), so
    landing on the horizontal target (orientation = +-90 deg) just needs
    the difference between where we are and 90 deg.
    """
    return 90.0 - math.degrees(orientation_rad)


def rotate_to_horizontal(specimen_img: np.ndarray, specimen_mask: np.ndarray, margin: int = 40) -> RotatedCrop:
    axes = compute_axes(specimen_mask)
    rot_deg = _rotation_degrees_for_horizontal(axes.orientation_rad)

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
    cropped_axes = compute_axes(cropped_mask)

    return RotatedCrop(image=cropped_img, mask=cropped_mask, axes=cropped_axes)
