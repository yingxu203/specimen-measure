# -*- coding: utf-8 -*-
"""
merge_manual_annotations.py

Takes an existing batch of automatic results (measurements.csv, from a
previous specimen-measure run) plus manual corrections recorded with
annotate_specimen.py, and produces a new results folder where the manual
length/width replace the automatic ones for whichever files were annotated.
Everything else is left untouched.

The manual annotation only records where you clicked (in pixels), not a
mm value -- this script converts those pixel clicks to mm using that same
file's own already-computed px_per_mm scale (rotating/cropping a photo
doesn't change its scale, so this is correct whether you annotated the raw
photo or its rotated/cropped overlay).

The manual FRAME (2 corner clicks) only gives a bounding box, not the true
segmented outline, so the area computed from it is an approximation (it
will typically overestimate area for a non-rectangular specimen) -- rows
corrected this way are flagged in a new "manually_corrected" column and a
note is added, so this is visible rather than silently looking as precise
as the automatic segmentation-based area.

USAGE:
    python merge_manual_annotations.py --results-dir results/v9 --output-dir results/v9_manual_merged
    (uses annotation_reference/reference_annotations_v2_with_frame.csv by default)
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from specimen_measure.cli import summarize_by_animal_and_view  # noqa: E402

DEFAULT_ANNOTATIONS_CSV = Path("annotation_reference/reference_annotations_v2_with_frame.csv")
CORRECTION_NOTE = "manually re-measured (area is bounding-box approx, not true segmented area)"


def _norm_stem(filename: str) -> str:
    """Normalize a filename to match a raw photo against an annotation
    that may have been made on its "_overlay" render instead."""
    stem = Path(filename).stem
    if stem.endswith("_overlay"):
        stem = stem[: -len("_overlay")]
    return stem.lower()


def merge_manual_annotations(
    results_dir: Path,
    annotations_csv: Path,
    output_dir: Path,
) -> pd.DataFrame:
    results = pd.read_csv(results_dir / "measurements.csv")
    annotations = pd.read_csv(annotations_csv)

    results["notes"] = results["notes"].astype("object")  # may load as all-NaN float64
    results["_stem"] = results["filename"].map(_norm_stem)
    annotations["_stem"] = annotations["filename"].map(_norm_stem)
    results["manually_corrected"] = False

    unmatched = []
    for _, arow in annotations.iterrows():
        matches = results.index[results["_stem"] == arow["_stem"]]
        if len(matches) == 0:
            unmatched.append(arow["filename"])
            continue
        idx = matches[0]

        px_per_mm = results.loc[idx, "px_per_mm"]
        if pd.isna(px_per_mm) or px_per_mm <= 0:
            unmatched.append(f"{arow['filename']} (matched file has no valid px_per_mm)")
            continue

        results.loc[idx, "long_axis_mm"] = arow["length_px"] / px_per_mm
        results.loc[idx, "short_axis_mm"] = arow["width_px"] / px_per_mm
        if pd.notna(arow.get("frame_width_px")) and pd.notna(arow.get("frame_height_px")):
            results.loc[idx, "area_mm2"] = (
                arow["frame_width_px"] * arow["frame_height_px"] / (px_per_mm ** 2)
            )
        results.loc[idx, "manually_corrected"] = True
        prior_notes = results.loc[idx, "notes"]
        results.loc[idx, "notes"] = (
            f"{prior_notes}; {CORRECTION_NOTE}" if pd.notna(prior_notes) and prior_notes
            else CORRECTION_NOTE
        )

    results = results.drop(columns=["_stem"])

    output_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_dir / "measurements.csv", index=False)

    summary = summarize_by_animal_and_view(results)
    if len(summary):
        summary.to_csv(output_dir / "summary_by_animal_and_view.csv", index=False)

    excel_path = output_dir / "measurements.xlsx"
    with pd.ExcelWriter(excel_path) as writer:
        results.to_excel(writer, sheet_name="measurements", index=False)
        if len(summary):
            summary.to_excel(writer, sheet_name="summary_by_animal_and_view", index=False)

    n_corrected = int(results["manually_corrected"].sum())
    print(f"Merged {n_corrected} manually-annotated image(s) into the results.")
    if unmatched:
        print(f"{len(unmatched)} annotation(s) did not match any file in measurements.csv:")
        for fn in unmatched:
            print(f"    {fn}")
    print(f"Merged results written to {output_dir}")

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, type=Path,
                         help="Folder containing the existing measurements.csv from a batch run.")
    parser.add_argument("--annotations-csv", type=Path, default=DEFAULT_ANNOTATIONS_CSV,
                         help=f"Manual annotation CSV from annotate_specimen.py "
                              f"(default: {DEFAULT_ANNOTATIONS_CSV}).")
    parser.add_argument("--output-dir", required=True, type=Path,
                         help="New folder to write the merged measurements.csv/.xlsx into "
                              "(never overwrites --results-dir).")
    args = parser.parse_args(argv)

    if not (args.results_dir / "measurements.csv").exists():
        parser.error(f"{args.results_dir / 'measurements.csv'} not found")
    if not args.annotations_csv.exists():
        parser.error(f"{args.annotations_csv} not found -- annotate some images first "
                      f"with annotate_specimen.py")

    merge_manual_annotations(args.results_dir, args.annotations_csv, args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
