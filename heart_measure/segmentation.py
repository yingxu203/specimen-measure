"""Segment the heart specimen from its dark background.

The specimen tissue (pale ventricle, red atria/vessels, white fibrous rim) is
much brighter than the near-black background in at least one color channel,
even where its overall brightness is low (e.g. deep red tissue with low
green/blue). Thresholding on the HSV "value" channel (max of R, G, B) instead
of plain grayscale mean captures the full tissue outline, including reddish
regions that a mean-brightness threshold would clip.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from skimage import filters, measure, morphology


class SegmentationError(RuntimeError):
    """Raised when no plausible specimen region can be found."""


@dataclass
class HeartRegion:
    mask: np.ndarray            # full-image boolean mask of the specimen
    area_px: float
    major_axis_length_px: float
    minor_axis_length_px: float
    centroid: tuple[float, float]   # (row, col)
    orientation_rad: float
    touches_frame_edge: bool        # QC flag: mask touches top/bottom/near edge


def segment_heart(
    img: np.ndarray,
    ruler_side: str,
    ruler_edge_px: int,
    min_size: int = 300,
    closing_radius: int = 4,
    hole_area: int = 5000,
) -> HeartRegion:
    """Segment the largest specimen blob in the non-ruler part of the frame."""
    h, w = img.shape[:2]
    value = img[:, :, :3].max(axis=2).astype(float) / 255.0

    if ruler_side == "right":
        region = value[:, :ruler_edge_px]
        col_offset = 0
    else:
        region = value[:, ruler_edge_px:]
        col_offset = ruler_edge_px

    if region.size == 0:
        raise SegmentationError("No non-ruler region to segment.")

    thresh = filters.threshold_otsu(region)
    mask = region > thresh
    mask = morphology.remove_small_objects(mask, min_size=min_size)
    mask = morphology.binary_closing(mask, morphology.disk(closing_radius))
    mask = morphology.remove_small_holes(mask, area_threshold=hole_area)

    labeled = measure.label(mask)
    props = measure.regionprops(labeled)
    if not props:
        raise SegmentationError("Otsu threshold + cleanup left no candidate regions.")

    biggest = max(props, key=lambda p: p.area)

    full_mask = np.zeros((h, w), dtype=bool)
    full_mask[:, col_offset:col_offset + region.shape[1]] = labeled == biggest.label

    min_row, min_col, max_row, max_col = biggest.bbox
    min_col += col_offset
    max_col += col_offset
    edge_margin = 3
    touches_edge = (
        min_row <= edge_margin
        or max_row >= h - edge_margin
        or (ruler_side == "right" and min_col <= edge_margin)
        or (ruler_side == "left" and max_col >= w - edge_margin)
    )

    return HeartRegion(
        mask=full_mask,
        area_px=float(biggest.area),
        major_axis_length_px=float(biggest.major_axis_length),
        minor_axis_length_px=float(biggest.minor_axis_length),
        centroid=(biggest.centroid[0], biggest.centroid[1] + col_offset),
        orientation_rad=float(biggest.orientation),
        touches_frame_edge=bool(touches_edge),
    )
