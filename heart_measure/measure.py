"""Per-image measurement: load a TIFF, calibrate its ruler, segment the heart,
and convert axis lengths from pixels to millimeters.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import tifffile

from .calibration import Calibration, CalibrationError, calibrate
from .metadata import SpecimenInfo, parse_filename
from .rotate import rotate_to_horizontal
from .segmentation import HeartRegion, SegmentationError, segment_heart

# Axis-line color by genotype, per lab convention: OX/OF/OM animals are OX
# genotype (red), WT/WF/WM animals are WT genotype (blue).
GENOTYPE_COLORS: dict[str, tuple[int, int, int]] = {
    "OX": (255, 44, 44),   # #FF2C2C
    "WT": (0, 0, 255),     # #0000FF
}
DEFAULT_AXIS_COLOR = (160, 160, 160)  # genotype not recognized from filename

# Below this many detected ruler ticks, the fitted px/mm scale is noticeably
# less stable (see README "Calibration confidence") -- flag rather than trust
# silently. Full-height rulers in this dataset typically yield 11-14 ticks;
# a tilted/cropped/overexposed ruler that still clears the hard minimum can
# land at 5-9 and measurably disagree with a same-animal sibling photo.
MIN_CONFIDENT_TICKS = 10


@dataclass
class MeasurementResult:
    filename: str
    ok: bool
    error: str | None
    long_axis_mm: float | None
    short_axis_mm: float | None
    area_mm2: float | None
    px_per_mm: float | None
    n_ruler_ticks: int | None
    ruler_side: str | None
    touches_frame_edge: bool | None
    low_confidence_calibration: bool | None
    genotype: str | None
    treatment: str | None
    animal_id: str | None
    view: str | None
    replicate: int | None
    cohort: int | None
    is_sv_variant: bool
    notes: str | None

    def to_row(self) -> dict:
        return asdict(self)


def load_image(path: Path) -> np.ndarray:
    arr = tifffile.imread(str(path))
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    if arr.ndim == 3 and arr.shape[2] > 3:
        arr = arr[:, :, :3]
    if arr.dtype != np.uint8:
        # Normalize any higher bit-depth source to 8-bit for consistent thresholds.
        arr = arr.astype(np.float64)
        arr -= arr.min()
        max_val = arr.max()
        if max_val > 0:
            arr = arr / max_val * 255.0
        arr = arr.astype(np.uint8)
    return arr


def measure_file(
    path: Path,
    ruler_side: str = "auto",
    overlay_path: Path | None = None,
) -> MeasurementResult:
    info = parse_filename(path.name)
    base_fields = dict(
        filename=path.name,
        genotype=info.genotype,
        treatment=info.treatment,
        animal_id=info.animal_id,
        view=info.view,
        replicate=info.replicate,
        cohort=info.cohort,
        is_sv_variant=info.is_sv_variant,
        notes=info.notes,
    )

    try:
        img = load_image(path)
    except Exception as exc:  # noqa: BLE001 - surface any decode failure per-file
        return MeasurementResult(
            ok=False, error=f"failed to read image: {exc}",
            long_axis_mm=None, short_axis_mm=None, area_mm2=None,
            px_per_mm=None, n_ruler_ticks=None, ruler_side=None,
            touches_frame_edge=None, low_confidence_calibration=None, **base_fields,
        )

    gray = img[:, :, :3].mean(axis=2)

    try:
        cal: Calibration = calibrate(gray, ruler_side=ruler_side)
    except CalibrationError as exc:
        return MeasurementResult(
            ok=False, error=f"calibration failed: {exc}",
            long_axis_mm=None, short_axis_mm=None, area_mm2=None,
            px_per_mm=None, n_ruler_ticks=None, ruler_side=None,
            touches_frame_edge=None, low_confidence_calibration=None, **base_fields,
        )
    low_confidence = cal.n_ticks < MIN_CONFIDENT_TICKS

    try:
        region: HeartRegion = segment_heart(img, cal.ruler_side, cal.ruler_edge_px)
    except SegmentationError as exc:
        return MeasurementResult(
            ok=False, error=f"segmentation failed: {exc}",
            long_axis_mm=None, short_axis_mm=None, area_mm2=None,
            px_per_mm=cal.px_per_mm, n_ruler_ticks=cal.n_ticks, ruler_side=cal.ruler_side,
            touches_frame_edge=None, low_confidence_calibration=low_confidence, **base_fields,
        )

    long_axis_mm = region.major_axis_length_px / cal.px_per_mm
    short_axis_mm = region.minor_axis_length_px / cal.px_per_mm
    area_mm2 = region.area_px / (cal.px_per_mm ** 2)

    if overlay_path is not None:
        _save_overlay(img, cal, region, info.genotype, long_axis_mm, short_axis_mm, area_mm2, overlay_path)

    return MeasurementResult(
        ok=True, error=None,
        long_axis_mm=long_axis_mm, short_axis_mm=short_axis_mm, area_mm2=area_mm2,
        px_per_mm=cal.px_per_mm, n_ruler_ticks=cal.n_ticks, ruler_side=cal.ruler_side,
        touches_frame_edge=region.touches_frame_edge, low_confidence_calibration=low_confidence,
        **base_fields,
    )


def _save_overlay(
    img: np.ndarray,
    cal: Calibration,
    region: HeartRegion,
    genotype: str | None,
    long_axis_mm: float,
    short_axis_mm: float,
    area_mm2: float,
    out_path: Path,
) -> None:
    """Draw the heart outline and axis lines on a copy of the specimen crop
    that has been rotated so the long axis is horizontal (parallel to the
    bottom edge), for easy visual comparison across many photos. The ruler
    is cropped out of this view -- it isn't needed for the drawing, and the
    displayed numbers (computed from the original, unrotated measurement)
    are the authoritative ones regardless of the rotation.
    """
    from PIL import Image, ImageDraw
    from skimage import measure as sk_measure

    w = img.shape[1]
    if cal.ruler_side == "right":
        specimen_img = img[:, :cal.ruler_edge_px]
        specimen_mask = region.mask[:, :cal.ruler_edge_px]
    else:
        specimen_img = img[:, cal.ruler_edge_px:]
        specimen_mask = region.mask[:, cal.ruler_edge_px:]

    crop = rotate_to_horizontal(specimen_img, specimen_mask)

    pil = Image.fromarray(crop.image).convert("RGB")
    draw = ImageDraw.Draw(pil)

    for contour in sk_measure.find_contours(crop.mask.astype(float), 0.5):
        draw.line([(x, y) for y, x in contour], fill=(0, 255, 0), width=3)

    color = GENOTYPE_COLORS.get(genotype or "", DEFAULT_AXIS_COLOR)
    (mx1, my1), (mx2, my2) = crop.axes.major_endpoints
    draw.line([(mx1, my1), (mx2, my2)], fill=color, width=3)
    (nx1, ny1), (nx2, ny2) = crop.axes.minor_endpoints
    draw.line([(nx1, ny1), (nx2, ny2)], fill=color, width=2)
    # "L"/"W" end-cap labels so the two same-colored lines stay distinguishable.
    draw.text((mx2 + 4, my2 - 6), "L", fill=color)
    draw.text((nx2 + 4, ny2 - 6), "W", fill=color)

    label = (
        f"long {long_axis_mm:.2f} mm | short {short_axis_mm:.2f} mm | area {area_mm2:.2f} mm2 | "
        f"{cal.px_per_mm:.1f} px/mm | {cal.n_ticks} ticks"
    )
    if cal.n_ticks < MIN_CONFIDENT_TICKS:
        label += "  [LOW-CONFIDENCE CALIBRATION]"
    draw.text((10, 10), label, fill=(255, 255, 0))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pil.save(out_path)
