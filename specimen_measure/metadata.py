# Created on 7/30/26
# @author: yingxu203
"""Best-effort extraction of experiment metadata from specimen photo filenames.

These filenames were typed by hand across many sessions and are not fully
consistent (extra spaces, inconsistent capitalization, occasional free-text
notes like "NO RA" or "NOT ALIGNED"). Every field here is optional: if a
pattern doesn't match, the field is left as None rather than raising, so a
batch run never fails because of a filename quirk.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_GENOTYPE_RE = re.compile(r"\b(WT|OX)\b", re.IGNORECASE)
_TREATMENT_RE = re.compile(r"\b(PF ISO|ISO|PF|VEH)\b", re.IGNORECASE)
_ANIMAL_ID_RE = re.compile(r"\b([A-Za-z]{1,2}\d{1,3}) *(?=(?:FRONT|BACK))", re.IGNORECASE)
_VIEW_RE = re.compile(r"\b(FRONT|BACK)\b", re.IGNORECASE)
_REP_RE = re.compile(r"(?:FRONT|BACK) *(\d+)", re.IGNORECASE)
_NOTES_RE = re.compile(r"(?:FRONT|BACK) *\d+ *([A-Za-z][A-Za-z ]*?)(?: ch\d+|$)", re.IGNORECASE)
_COHORT_RE = re.compile(r"treated (\d+)", re.IGNORECASE)


def _normalize(stem: str) -> str:
    """Replace filename delimiters with spaces so \\b word boundaries behave;
    Python's \\b treats '_' as a word char, so '1_ISO' would otherwise fail to
    match '\\bISO\\b'.
    """
    return re.sub(r"[_\-]+", " ", stem)


@dataclass
class SpecimenInfo:
    genotype: str | None
    treatment: str | None
    animal_id: str | None
    view: str | None
    replicate: int | None
    cohort: int | None
    is_sv_variant: bool
    notes: str | None


def parse_filename(filename: str) -> SpecimenInfo:
    stem = filename
    for ext in (".tif", ".tiff"):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break

    norm = _normalize(stem)

    genotype_m = _GENOTYPE_RE.search(norm)
    treatment_m = _TREATMENT_RE.search(norm)
    animal_m = _ANIMAL_ID_RE.search(norm)
    view_m = _VIEW_RE.search(norm)
    rep_m = _REP_RE.search(norm)
    notes_m = _NOTES_RE.search(norm)
    cohort_m = _COHORT_RE.search(norm)

    notes = notes_m.group(1).strip(" -") if notes_m else None
    if notes == "":
        notes = None

    genotype = genotype_m.group(1).upper() if genotype_m else None
    animal_id = animal_m.group(1).upper() if animal_m else None
    if genotype is None and animal_id:
        # Some filenames (mostly "_SV" duplicates) drop the standalone
        # genotype word but keep the animal ID, which itself encodes the
        # genotype by the same lab convention used for axis-line coloring:
        # O* (OM/OF/OX) animals are OX genotype, W* (WM/WF/WT) are WT.
        # Verified to hold with zero exceptions across the full dataset
        # this was built against before relying on it as a fallback.
        if animal_id[0] == "O":
            genotype = "OX"
        elif animal_id[0] == "W":
            genotype = "WT"

    return SpecimenInfo(
        genotype=genotype,
        treatment=re.sub(r"\s+", " ", treatment_m.group(1)).upper() if treatment_m else None,
        animal_id=animal_id,
        view=view_m.group(1).upper() if view_m else None,
        replicate=int(rep_m.group(1)) if rep_m else None,
        cohort=int(cohort_m.group(1)) if cohort_m else None,
        is_sv_variant=stem.lower().endswith("_sv") or "_sv_" in stem.lower(),
        notes=notes,
    )
