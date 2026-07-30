"""Command-line entry point: batch-measure every specimen photo in a folder.

Usage:
    python -m heart_measure.cli --input-dir "/path/to/photos" --output-dir ./results
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .measure import MIN_CONFIDENT_TICKS, measure_file
from .rotate import OrientMode

DEFAULT_PATTERN = "*.tif"


def find_images(input_dir: Path, pattern: str) -> list[Path]:
    return sorted(p for p in input_dir.rglob(pattern) if p.is_file())


def summarize_by_animal_and_view(df: pd.DataFrame) -> pd.DataFrame:
    """Mean +/- std per (genotype, treatment, animal_id, view).

    Grouping includes `view` so FRONT and BACK photos of the same animal are
    always summarized separately, never pooled together -- a front photo's
    apparent long/short axis isn't directly comparable to a back photo's.
    """
    ok = df[df["ok"]]
    if not len(ok) or not ok["animal_id"].notna().any():
        return pd.DataFrame()
    return (
        ok.dropna(subset=["animal_id"])
        .groupby(["genotype", "treatment", "animal_id", "view"], dropna=False)
        .agg(
            n=("long_axis_mm", "size"),
            long_axis_mm_mean=("long_axis_mm", "mean"),
            long_axis_mm_std=("long_axis_mm", "std"),
            short_axis_mm_mean=("short_axis_mm", "mean"),
            short_axis_mm_std=("short_axis_mm", "std"),
            area_mm2_mean=("area_mm2", "mean"),
            area_mm2_std=("area_mm2", "std"),
        )
        .reset_index()
    )


def run(
    input_dir: Path,
    output_dir: Path,
    pattern: str,
    ruler_side: str,
    overlays: bool,
    orient_mode: OrientMode = "apex_down",
    use_genotype_colors: bool = True,
) -> pd.DataFrame:
    files = find_images(input_dir, pattern)
    if not files:
        raise SystemExit(f"No files matching {pattern!r} found under {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir = output_dir / "overlays"

    rows = []
    for path in files:
        overlay_path = overlay_dir / f"{path.stem}_overlay.png" if overlays else None
        result = measure_file(
            path, ruler_side=ruler_side, overlay_path=overlay_path,
            orient_mode=orient_mode, use_genotype_colors=use_genotype_colors,
        )
        rows.append(result.to_row())
        status = "ok" if result.ok else f"FAILED: {result.error}"
        print(f"{path.name}: {status}")

    df = pd.DataFrame(rows)
    df.to_csv(output_dir / "measurements.csv", index=False)

    ok = df[df["ok"]]
    n_failed = len(df) - len(ok)
    print(f"\n{len(ok)}/{len(df)} images measured successfully.")
    if n_failed:
        print(f"{n_failed} image(s) failed — see the 'error' column in measurements.csv.")
    flagged = ok[ok["touches_frame_edge"]]
    if len(flagged):
        print(f"{len(flagged)} image(s) have a heart mask touching the frame edge — "
              f"worth a visual check (possible crop/clipping).")
    low_conf = ok[ok["low_confidence_calibration"]]
    if len(low_conf):
        print(f"{len(low_conf)} image(s) have a low-confidence ruler calibration "
              f"(fewer than {MIN_CONFIDENT_TICKS} ticks found, usually from a tilted/overexposed "
              f"ruler) — their mm values may be off by ~10-20%; check the overlay and consider "
              f"measuring these by hand:")
        for fn in low_conf["filename"]:
            print(f"    {fn}")

    summary = summarize_by_animal_and_view(df)
    if len(summary):
        summary.to_csv(output_dir / "summary_by_animal_and_view.csv", index=False)

    return df


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path,
                         help="Folder containing specimen TIFF photos (searched recursively).")
    parser.add_argument("--output-dir", default=Path("./results"), type=Path,
                         help="Where to write measurements.csv and overlay images (default: ./results).")
    parser.add_argument("--pattern", default=DEFAULT_PATTERN,
                         help=f"Glob pattern for image files (default: {DEFAULT_PATTERN!r}).")
    parser.add_argument("--ruler-side", default="auto", choices=["auto", "left", "right"],
                         help="Which edge of the frame the ruler is on (default: auto-detect).")
    parser.add_argument("--no-overlays", action="store_true",
                         help="Skip writing annotated QC overlay images (faster, smaller output).")
    parser.add_argument("--orientation", default="apex_down",
                         choices=["apex_down", "vertical", "horizontal"],
                         help="Overlay orientation convention (default: apex_down, a heart-specific "
                              "convention -- atria/base up, apex down). Use 'vertical' or 'horizontal' "
                              "for other organs/tumors with no consistent 'this end goes on top'.")
    parser.add_argument("--no-genotype-colors", action="store_true",
                         help="Don't color axis lines by the OX/WT heart-study genotype convention; "
                              "use a single neutral color for all images.")
    args = parser.parse_args(argv)

    if not args.input_dir.is_dir():
        parser.error(f"--input-dir {args.input_dir} is not a directory")

    run(
        args.input_dir, args.output_dir, args.pattern, args.ruler_side, overlays=not args.no_overlays,
        orient_mode=args.orientation, use_genotype_colors=not args.no_genotype_colors,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
