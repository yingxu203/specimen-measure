"""Command-line entry point: batch-measure every specimen photo in a folder.

Usage:
    python -m specimen_measure.cli --input-dir "/path/to/photos" --output-dir ./results
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .contact_sheet import build_overlay_pdf
from .measure import MIN_CONFIDENT_TICKS, measure_file
from .metadata import parse_filename
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


def _flip_key(filename: str) -> tuple[str | None, str | None, int | None]:
    info = parse_filename(filename)
    return (info.animal_id, info.view, info.replicate)


def expand_force_flip(filenames: list[str], all_files: list[Path]) -> set[str]:
    """Given exact filenames known to need a manual orientation flip, also
    flip any other file sharing the same (animal_id, view, replicate) --
    e.g. a "_SV" duplicate export of the same photo -- so a correction only
    has to be given once per physical photo, not once per file variant.
    """
    keys = {_flip_key(f) for f in filenames}
    keys.discard((None, None, None))
    matched = {f.name for f in all_files if _flip_key(f.name) in keys}
    return matched | set(filenames)


def run(
    input_dir: Path,
    output_dir: Path,
    pattern: str,
    ruler_side: str,
    overlays: bool,
    orient_mode: OrientMode = "apex_down",
    use_genotype_colors: bool = True,
    force_flip: list[str] | None = None,
    genotype_labels: tuple[str, str] | None = None,
) -> pd.DataFrame:
    files = find_images(input_dir, pattern)
    if not files:
        raise SystemExit(f"No files matching {pattern!r} found under {input_dir}")

    flip_set = expand_force_flip(force_flip, files) if force_flip else set()

    output_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir = output_dir / "overlays"

    rows = []
    overlay_paths = []
    for path in files:
        overlay_path = overlay_dir / f"{path.stem}_overlay.png" if overlays else None
        result = measure_file(
            path, ruler_side=ruler_side, overlay_path=overlay_path,
            orient_mode=orient_mode, use_genotype_colors=use_genotype_colors,
            manual_flip=path.name in flip_set, genotype_labels=genotype_labels,
        )
        rows.append(result.to_row())
        status = "ok" if result.ok else f"FAILED: {result.error}"
        if path.name in flip_set:
            status += " (force-flipped)"
        print(f"{path.name}: {status}")
        if overlay_path is not None and overlay_path.exists():
            overlay_paths.append(overlay_path)

    df = pd.DataFrame(rows)
    df.to_csv(output_dir / "measurements.csv", index=False)

    ok = df[df["ok"]]
    n_failed = len(df) - len(ok)
    print(f"\n{len(ok)}/{len(df)} images measured successfully.")
    if n_failed:
        print(f"{n_failed} image(s) failed — see the 'error' column in measurements.csv.")
    flagged = ok[ok["touches_frame_edge"]]
    if len(flagged):
        print(f"{len(flagged)} image(s) have a specimen mask touching the frame edge — "
              f"worth a visual check (possible crop/clipping).")
    low_conf = ok[ok["low_confidence_calibration"]]
    if len(low_conf):
        print(f"{len(low_conf)} image(s) have a low-confidence ruler calibration "
              f"(fewer than {MIN_CONFIDENT_TICKS} ticks found, usually from a tilted/overexposed "
              f"ruler) — their mm values may be off by ~10-20%; check the overlay and consider "
              f"measuring these by hand:")
        for fn in low_conf["filename"]:
            print(f"    {fn}")
    low_orient = ok[ok["low_confidence_orientation"].fillna(False)]
    if len(low_orient):
        print(f"{len(low_orient)} image(s) have a low-confidence apex/base orientation guess "
              f"(the atria/ventricle split was a close call) — mm values are unaffected, but the "
              f"overlay may show it upside down; check the overlay and use the UI's flip checkbox "
              f"if so:")
        for fn in low_orient["filename"]:
            print(f"    {fn}")

    summary = summarize_by_animal_and_view(df)
    if len(summary):
        summary.to_csv(output_dir / "summary_by_animal_and_view.csv", index=False)

    if overlay_paths:
        pdf_path = output_dir / "overlays_combined.pdf"
        build_overlay_pdf(overlay_paths, pdf_path)
        print(f"\nAll {len(overlay_paths)} overlay(s) combined into {pdf_path} for easy scrolling review.")

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
                         choices=["apex_down", "none"],
                         help="Measurement/orientation mode (default: apex_down). 'apex_down' is the "
                              "heart-specific convention: rotates atria/base up, apex down, and "
                              "measures width excluding the atria. 'none' is for other tissue/tumors: "
                              "no rotation, and length/width simply cross the specimen's own center "
                              "and stop at its edge.")
    parser.add_argument("--no-genotype-colors", action="store_true",
                         help="Don't color axis lines by the OX/WT heart-study genotype convention; "
                              "use a single neutral color for all images.")
    parser.add_argument("--force-flip", nargs="+", default=[], metavar="FILENAME",
                         help="Filenames (apex_down mode) known to have the wrong automatic "
                              "apex/base orientation -- flips these regardless of what the "
                              "heuristic decides. Any other file sharing the same animal ID, "
                              "view, and replicate number (e.g. a '_SV' duplicate export) is "
                              "flipped too, so you only need to list a correction once per photo.")
    args = parser.parse_args(argv)

    if not args.input_dir.is_dir():
        parser.error(f"--input-dir {args.input_dir} is not a directory")

    run(
        args.input_dir, args.output_dir, args.pattern, args.ruler_side, overlays=not args.no_overlays,
        orient_mode=args.orientation, use_genotype_colors=not args.no_genotype_colors,
        force_flip=args.force_flip,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
