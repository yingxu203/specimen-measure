from pathlib import Path

from specimen_measure.cli import expand_force_flip


def test_expand_force_flip_matches_sv_duplicate():
    """A correction given for one photo should also apply to any other file
    variant of the same physical photo (e.g. a "_SV" duplicate export),
    identified by matching animal ID + view + replicate number, so a
    correction only needs to be listed once."""
    files = [
        Path("AKAP12 WT OSMOTIC PUMP TREATED 1 (1)_ISO WF15_BACK-2_ch00.tif"),
        Path("AKAP12 WT OSMOTIC PUMP TREATED 1_ISO WF15_BACK-2_ch00_SV.tif"),
        Path("AKAP12 WT OSMOTIC PUMP TREATED 1 (1)_ISO WF15_BACK-1_ch00.tif"),
    ]
    flip_set = expand_force_flip(
        ["AKAP12 WT OSMOTIC PUMP TREATED 1 (1)_ISO WF15_BACK-2_ch00.tif"], files,
    )
    assert "AKAP12 WT OSMOTIC PUMP TREATED 1_ISO WF15_BACK-2_ch00_SV.tif" in flip_set
    assert "AKAP12 WT OSMOTIC PUMP TREATED 1 (1)_ISO WF15_BACK-1_ch00.tif" not in flip_set


def test_expand_force_flip_keeps_explicit_names_even_if_unparseable():
    files = [Path("some_unrelated_filename.tif")]
    flip_set = expand_force_flip(["some_unrelated_filename.tif"], files)
    assert "some_unrelated_filename.tif" in flip_set
