from specimen_measure.metadata import parse_filename


def test_parses_typical_filename():
    info = parse_filename("AKAP12  OX osmotic pump treated 1_PF ISO OM17_BACK-1_ch00.tif")
    assert info.genotype == "OX"
    assert info.treatment == "PF ISO"
    assert info.animal_id == "OM17"
    assert info.view == "BACK"
    assert info.replicate == 1
    assert info.notes is None
    assert not info.is_sv_variant


def test_parses_notes_and_sv_variant():
    info = parse_filename("AKAP12 WT OSMOTIC PUMP TREATED 1 (1)_PF WF7_BACK-1 NO RA_ch00.tif")
    assert info.animal_id == "WF7"
    assert info.notes == "NO RA"

    info_sv = parse_filename("AKAP12 WT OSMOTIC PUMP TREATED 1_ISO WF15_BACK-2_ch00_SV.tif")
    assert info_sv.is_sv_variant
    assert info_sv.animal_id == "WF15"


def test_genotype_falls_back_to_animal_id_prefix():
    """Some "_SV" duplicate filenames drop the standalone genotype word but
    keep the animal ID, which encodes genotype by the same O*/W* convention
    used for axis-line coloring -- confirmed to have found the axis lines
    on such a file rendering in the fallback (unclassified) color instead
    of the correct genotype color."""
    info = parse_filename("AKAP12 osmotic pump treated 1_ISO OX14_BACK-1_ch00_SV.tif")
    assert info.genotype == "OX"
    assert info.animal_id == "OX14"

    info_w = parse_filename("AKAP12 osmotic pump treated 1_ISO WM9_BACK-1_ch00_SV.tif")
    assert info_w.genotype == "WT"


def test_missing_fields_are_none_not_raising():
    info = parse_filename("some_unrelated_filename.tif")
    assert info.genotype is None
    assert info.animal_id is None
    assert info.view is None
