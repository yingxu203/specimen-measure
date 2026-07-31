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

The manual FRAME is a hand-traced outline (however many points you clicked
around the tissue), so its area is the true polygon area, not a bounding-box
approximation. Rows corrected this way are flagged in a new
"manually_corrected" column and a note is added.

USAGE:
    python merge_manual_annotations.py --results-dir results/v9 --output-dir results/v9_manual_merged
    (uses annotation_reference/reference_annotations_v3_polygon_frame.csv by default)
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from annotate_specimen import polygon_area_px  # noqa: E402
from specimen_measure.cli import summarize_by_animal_and_view  # noqa: E402

DEFAULT_ANNOTATIONS_CSV = Path("annotation_reference/reference_annotations_v3_polygon_frame.csv")
CORRECTION_NOTE_TEMPLATE = "manually re-measured (area from a {n}-point hand-traced outline)"


def _parse_frame_points(frame_points_px) -> list[tuple[float, float]]:
    if not isinstance(frame_points_px, str) or not frame_points_px.strip():
        return []
    points = []
    for part in frame_points_px.split(";"):
        x_str, y_str = part.split(",")
        points.append((float(x_str), float(y_str)))
    return points


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

        frame_points = _parse_frame_points(arow.get("frame_points_px"))
        note = CORRECTION_NOTE_TEMPLATE.format(n=len(frame_points))
        if len(frame_points) >= 3:
            area_px = polygon_area_px(frame_points)
            results.loc[idx, "area_mm2"] = area_px / (px_per_mm ** 2)
        else:
            note += " -- no outline traced, area_mm2 left as the automatic value"

        results.loc[idx, "manually_corrected"] = True
        prior_notes = results.loc[idx, "notes"]
        results.loc[idx, "notes"] = f"{prior_notes}; {note}" if pd.notna(prior_notes) and prior_notes else note

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
