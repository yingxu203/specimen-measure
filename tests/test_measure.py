from specimen_measure.measure import _resolve_genotype


def test_resolve_genotype_prefers_custom_label_found_in_filename():
    assert _resolve_genotype("Mutant1_FRONT-1_ch00.tif", None, ("Mutant", "Control")) == "Mutant"
    assert _resolve_genotype("Control1_FRONT-1_ch00.tif", None, ("Mutant", "Control")) == "Control"


def test_resolve_genotype_is_case_insensitive():
    assert _resolve_genotype("mutant1_FRONT-1.tif", None, ("Mutant", "Control")) == "Mutant"


def test_resolve_genotype_falls_back_when_no_custom_label_matches():
    assert _resolve_genotype("WM14_FRONT-1.tif", "WT", ("Mutant", "Control")) == "WT"


def test_resolve_genotype_returns_default_when_no_labels_given():
    assert _resolve_genotype("WM14_FRONT-1.tif", "WT", None) == "WT"
