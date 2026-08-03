# -*- coding: utf-8 -*-
"""
compute_annotation_measurements.py

The manual annotation tool (annotate_specimen.py) only records where you
clicked, in pixels -- it has no way to know the photo's mm scale on its own,
since it may be pointed at either the raw photo (ruler visible) or an
already-cropped overlay (ruler no longer in frame). This script converts
those pixel clicks into real length_mm / width_mm / area_mm2 by looking up
each annotated file's own already-computed px_per_mm ruler calibration from
an existing measurements.csv (from a specimen_measure batch run), matched by
filename.

This only adds columns to the annotation file itself -- it never touches the
original measurements.csv/.xlsx from the batch run.

USAGE:
    python compute_annotation_measurements.py --results-csv results/v9/measurements.csv
    (defaults to annotation_reference/reference_annotations_v3_polygon_frame.csv)
"""

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

DEFAULT_ANNOTATIONS_CSV = Path("annotation_reference/reference_annotations_v3_polygon_frame.csv")


def _norm_stem(filename: str) -> str:
    """Normalize a filename to match a raw photo against an annotation that
    may have been made on its "_overlay" render instead."""
    stem = Path(filename).stem
    if stem.endswith("_overlay"):
        stem = stem[: -len("_overlay")]
    return stem.lower()


def compute_annotation_measurements(annotations_csv: Path, results_csv: Path) -> tuple[pd.DataFrame, list[str]]:
    ann = pd.read_csv(annotations_csv)
    results = pd.read_csv(results_csv)

    ann["_stem"] = ann["filename"].map(_norm_stem)
    results["_stem"] = results["filename"].map(_norm_stem)
    lookup = results.drop_duplicates("_stem").set_index("_stem")[["px_per_mm", "low_confidence_calibration"]]

    ann = ann.join(lookup, on="_stem")
    unmatched = ann.loc[ann["px_per_mm"].isna(), "filename"].tolist()

    ann["length_mm"] = ann["length_px"] / ann["px_per_mm"]
    ann["width_mm"] = ann["width_px"] / ann["px_per_mm"]
    ann["area_mm2"] = ann["frame_area_px"] / (ann["px_per_mm"] ** 2)

    ann = ann.drop(columns=["_stem"])
    return ann, unmatched


def _backup(path: Path):
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations-csv", type=Path, default=DEFAULT_ANNOTATIONS_CSV,
                         help=f"Annotation CSV from annotate_specimen.py (default: {DEFAULT_ANNOTATIONS_CSV}).")
    parser.add_argument("--results-csv", required=True, type=Path,
                         help="An existing measurements.csv (from a specimen_measure batch run) "
                              "to look up each file's px_per_mm calibration from.")
    args = parser.parse_args(argv)

    if not args.annotations_csv.exists():
        parser.error(f"{args.annotations_csv} not found -- annotate some images first.")
    if not args.results_csv.exists():
        parser.error(f"{args.results_csv} not found.")

    ann, unmatched = compute_annotation_measurements(args.annotations_csv, args.results_csv)

    _backup(args.annotations_csv)
    ann.to_csv(args.annotations_csv, index=False)
    xlsx_path = args.annotations_csv.with_suffix(".xlsx")
    _backup(xlsx_path)
    ann.to_excel(xlsx_path, index=False)

    n_ok = len(ann) - len(unmatched)
    print(f"Computed length_mm / width_mm / area_mm2 for {n_ok}/{len(ann)} annotated image(s).")
    low_conf = ann[ann["low_confidence_calibration"].fillna(False)]
    if len(low_conf):
        print(f"{len(low_conf)} of these used a LOW-CONFIDENCE calibration in the source results "
              f"-- their mm values may be off by ~10-20%:")
        for fn in low_conf["filename"]:
            print(f"    {fn}")
    if unmatched:
        print(f"{len(unmatched)} annotation(s) had no matching file in {args.results_csv} "
              f"(px_per_mm left blank):")
        for fn in unmatched:
            print(f"    {fn}")
    print(f"Updated: {args.annotations_csv}")
    print(f"Updated: {xlsx_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
