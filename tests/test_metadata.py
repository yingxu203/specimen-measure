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


def test_missing_fields_are_none_not_raising():
    info = parse_filename("some_unrelated_filename.tif")
    assert info.genotype is None
    assert info.animal_id is None
    assert info.view is None
