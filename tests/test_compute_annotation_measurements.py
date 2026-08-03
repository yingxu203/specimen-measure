import pandas as pd

from compute_annotation_measurements import _norm_stem, compute_annotation_measurements


def test_norm_stem_matches_raw_file_to_its_overlay_render():
    assert _norm_stem("sample_WT01_FRONT-1_ch00.tif") == _norm_stem(
        "sample_WT01_FRONT-1_ch00_overlay.png"
    )


def test_computes_mm_from_matching_calibration(tmp_path):
    annotations_csv = tmp_path / "annotations.csv"
    pd.DataFrame([{
        "filename": "bad_overlay.png",
        "frame_points_px": "0,0;100,0;100,200;0,200",
        "frame_area_px": 100 * 200,
        "length_x1": 0, "length_y1": 0, "length_x2": 0, "length_y2": 200, "length_px": 200,
        "width_x1": 0, "width_y1": 0, "width_x2": 100, "width_y2": 0, "width_px": 100,
    }]).to_csv(annotations_csv, index=False)

    results_csv = tmp_path / "measurements.csv"
    pd.DataFrame([{
        "filename": "bad.tif", "px_per_mm": 20.0, "low_confidence_calibration": False,
    }]).to_csv(results_csv, index=False)

    ann, unmatched = compute_annotation_measurements(annotations_csv, results_csv)

    assert unmatched == []
    row = ann.iloc[0]
    assert row["length_mm"] == 200 / 20.0
    assert row["width_mm"] == 100 / 20.0
    assert row["area_mm2"] == (100 * 200) / (20.0 ** 2)


def test_reports_unmatched_filenames_without_crashing(tmp_path):
    annotations_csv = tmp_path / "annotations.csv"
    pd.DataFrame([{
        "filename": "no_such_file.png",
        "frame_points_px": "0,0;10,0;10,10;0,10", "frame_area_px": 100,
        "length_x1": 0, "length_y1": 0, "length_x2": 0, "length_y2": 10, "length_px": 10,
        "width_x1": 0, "width_y1": 0, "width_x2": 10, "width_y2": 0, "width_px": 10,
    }]).to_csv(annotations_csv, index=False)

    results_csv = tmp_path / "measurements.csv"
    pd.DataFrame([{
        "filename": "unrelated.tif", "px_per_mm": 20.0, "low_confidence_calibration": False,
    }]).to_csv(results_csv, index=False)

    ann, unmatched = compute_annotation_measurements(annotations_csv, results_csv)

    assert unmatched == ["no_such_file.png"]
    assert pd.isna(ann.iloc[0]["length_mm"])
