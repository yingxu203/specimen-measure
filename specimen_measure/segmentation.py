# Created on 7/30/26
# @author: yingxu203
"""Segment the heart specimen from its dark background.

The specimen tissue (pale ventricle, red atria/vessels, white fibrous rim) is
much brighter than the near-black background in at least one color channel,
even where its overall brightness is low (e.g. deep red tissue with low
green/blue). Thresholding on the HSV "value" channel (max of R, G, B) instead
of plain grayscale mean captures the full tissue outline, including reddish
regions that a mean-brightness threshold would clip.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from skimage import filters, measure, morphology


class SegmentationError(RuntimeError):
    """Raised when no plausible specimen region can be found."""


Point = tuple[float, float]  # (x, y) in image/array column-row coordinates


@dataclass
class AxesInfo:
    centroid_xy: Point
    orientation_rad: float
    major_endpoints: tuple[Point, Point]
    minor_endpoints: tuple[Point, Point]
    major_axis_length_px: float
    minor_axis_length_px: float


@dataclass
class HeartRegion:
    mask: np.ndarray            # full-image boolean mask of the specimen
    area_px: float
    touches_frame_edge: bool        # QC flag: mask touches top/bottom/near edge


def compute_axes(mask: np.ndarray) -> AxesInfo:
    """Measure the true physical extent of `mask` along its principal axes.

    `skimage.regionprops.major_axis_length` is the axis length of the
    *ellipse with equivalent second moments* -- for a shape with notches or
    asymmetric protrusions (like a heart with an auricle sticking out), that
    can be noticeably shorter or longer than the shape's actual reach along
    that direction.

    This instead projects every foreground pixel onto the principal-axis
    directions (still taken from image moments, since that's a stable
    estimate of orientation) purely to *identify* which two pixels are the
    extremes -- the endpoints actually returned/drawn are those two real
    pixels' own (x, y) coordinates, not their idealized position on the
    central axis line through the centroid. That distinction matters for
    asymmetric shapes: the pixel with the most extreme projection is often
    offset to one side of the centroid line (e.g. an auricle tip), so a line
    drawn between the *projected* positions would visibly fall short of, or
    poke past, the true boundary. Drawing between the real pixels guarantees
    the line touches the actual boundary at both ends, and the reported
    length (the Euclidean distance between them) matches what's drawn.
    """
    labeled = measure.label(mask)
    props = measure.regionprops(labeled)
    if not props:
        raise SegmentationError("compute_axes called on an empty mask.")
    biggest = max(props, key=lambda p: p.area)

    y0, x0 = biggest.centroid
    orientation = float(biggest.orientation)

    # Direction unit vectors as (dx, dy); matches the convention already used
    # for drawing (orientation is skimage's angle between the row axis and
    # the major axis).
    u_major = (math.sin(orientation), math.cos(orientation))
    u_minor = (math.cos(orientation), -math.sin(orientation))

    ys, xs = np.nonzero(mask)
    rel_x = xs - x0
    rel_y = ys - y0

    t_major = rel_x * u_major[0] + rel_y * u_major[1]
    t_minor = rel_x * u_minor[0] + rel_y * u_minor[1]

    i_maj_lo, i_maj_hi = int(np.argmin(t_major)), int(np.argmax(t_major))
    i_min_lo, i_min_hi = int(np.argmin(t_minor)), int(np.argmax(t_minor))

    def pixel(i: int) -> Point:
        return (float(xs[i]), float(ys[i]))

    def dist(p: Point, q: Point) -> float:
        return math.hypot(p[0] - q[0], p[1] - q[1])

    major_pts = (pixel(i_maj_lo), pixel(i_maj_hi))
    minor_pts = (pixel(i_min_lo), pixel(i_min_hi))

    return AxesInfo(
        centroid_xy=(x0, y0),
        orientation_rad=orientation,
        major_endpoints=major_pts,
        minor_endpoints=minor_pts,
        major_axis_length_px=dist(*major_pts),
        minor_axis_length_px=dist(*minor_pts),
    )


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
        touches_frame_edge=bool(touches_edge),
    )
