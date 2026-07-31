import pandas as pd

from merge_manual_annotations import _norm_stem, merge_manual_annotations


def test_norm_stem_matches_raw_file_to_its_overlay_render():
    assert _norm_stem("sample_WT01_FRONT-1_ch00.tif") == _norm_stem(
        "sample_WT01_FRONT-1_ch00_overlay.png"
    )


def test_merge_overwrites_only_annotated_rows(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    pd.DataFrame([
        {
            "filename": "good.tif", "ok": True, "error": None,
            "long_axis_mm": 10.0, "short_axis_mm": 5.0, "area_mm2": 40.0,
            "px_per_mm": 20.0, "n_ruler_ticks": 12, "ruler_side": "right",
            "touches_frame_edge": False, "low_confidence_calibration": False,
            "low_confidence_orientation": False, "genotype": "WT",
            "treatment": None, "animal_id": "W01", "view": "FRONT",
            "replicate": 1, "cohort": None, "is_sv_variant": False, "notes": None,
        },
        {
            "filename": "bad.tif", "ok": True, "error": None,
            "long_axis_mm": 999.0, "short_axis_mm": 999.0, "area_mm2": 999.0,
            "px_per_mm": 20.0, "n_ruler_ticks": 12, "ruler_side": "right",
            "touches_frame_edge": False, "low_confidence_calibration": False,
            "low_confidence_orientation": False, "genotype": "OX",
            "treatment": None, "animal_id": "O01", "view": "FRONT",
            "replicate": 1, "cohort": None, "is_sv_variant": False, "notes": None,
        },
    ]).to_csv(results_dir / "measurements.csv", index=False)

    annotations_csv = tmp_path / "annotations.csv"
    pd.DataFrame([{
        "filename": "bad_overlay.png",
        # a 100x200 rectangle traced as a 4-point outline -> polygon area == 100*200
        "frame_points_px": "0.00,0.00;100.00,0.00;100.00,200.00;0.00,200.00",
        "frame_area_px": 100 * 200,
        "length_x1": 0, "length_y1": 0, "length_x2": 0, "length_y2": 200, "length_px": 200,
        "width_x1": 0, "width_y1": 0, "width_x2": 100, "width_y2": 0, "width_px": 100,
    }]).to_csv(annotations_csv, index=False)

    output_dir = tmp_path / "merged"
    merged = merge_manual_annotations(results_dir, annotations_csv, output_dir)

    good = merged[merged["filename"] == "good.tif"].iloc[0]
    assert good["long_axis_mm"] == 10.0
    assert not good["manually_corrected"]

    bad = merged[merged["filename"] == "bad.tif"].iloc[0]
    assert bad["long_axis_mm"] == 200 / 20.0  # length_px / px_per_mm
    assert bad["short_axis_mm"] == 100 / 20.0
    assert bad["area_mm2"] == (100 * 200) / (20.0 ** 2)  # true polygon area, not a box approximation
    assert bad["manually_corrected"]
    assert "manually re-measured" in bad["notes"]
    assert "4-point" in bad["notes"]

    assert (output_dir / "measurements.csv").exists()
    assert (output_dir / "measurements.xlsx").exists()


def test_merge_reports_unmatched_annotations_without_crashing(tmp_path, capsys):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    pd.DataFrame([{
        "filename": "good.tif", "ok": True, "error": None,
        "long_axis_mm": 10.0, "short_axis_mm": 5.0, "area_mm2": 40.0,
        "px_per_mm": 20.0, "n_ruler_ticks": 12, "ruler_side": "right",
        "touches_frame_edge": False, "low_confidence_calibration": False,
        "low_confidence_orientation": False, "genotype": "WT",
        "treatment": None, "animal_id": "W01", "view": "FRONT",
        "replicate": 1, "cohort": None, "is_sv_variant": False, "notes": None,
    }]).to_csv(results_dir / "measurements.csv", index=False)

    annotations_csv = tmp_path / "annotations.csv"
    pd.DataFrame([{
        "filename": "no_such_file.png",
        "frame_points_px": "0.00,0.00;10.00,0.00;10.00,10.00;0.00,10.00",
        "frame_area_px": 100,
        "length_x1": 0, "length_y1": 0, "length_x2": 0, "length_y2": 10, "length_px": 10,
        "width_x1": 0, "width_y1": 0, "width_x2": 10, "width_y2": 0, "width_px": 10,
    }]).to_csv(annotations_csv, index=False)

    output_dir = tmp_path / "merged"
    merged = merge_manual_annotations(results_dir, annotations_csv, output_dir)

    assert not merged["manually_corrected"].any()
    assert "did not match" in capsys.readouterr().out
