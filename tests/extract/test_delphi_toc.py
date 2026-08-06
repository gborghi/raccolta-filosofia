# tests/extract/test_delphi_toc.py
from scripts.extract.delphi_toc import parse_toc

SENECA_TOC = """The Complete Works of

SENECA THE YOUNGER

(4 BC – AD 65)



Contents

The Tragedies

THE MADNESS OF HERCULES

MEDEA

The Essays

ON ANGER

ON THE SHORTNESS OF LIFE

The Latin Texts

LIST OF LATIN TEXTS

The Biography

INTRODUCTION TO SENECA by John W. Basore

The Delphi Classics Catalogue



© Delphi Classics 2014

Version 1
"""

HEGEL_TOC = """The Collected Works of

GEORG WILHELM FRIEDRICH HEGEL

(1770-1831)



Contents

The Books

The Phenomenology of Spirit

The Logic of Hegel

The Criticism

On Some Hegelisms by William James

© Delphi Classics 2015
"""


def test_parses_work_titles_with_sections():
    entries = parse_toc(SENECA_TOC)
    works = [(e.section, e.title) for e in entries if e.kind == "work"]
    assert works == [
        ("The Tragedies", "THE MADNESS OF HERCULES"),
        ("The Tragedies", "MEDEA"),
        ("The Essays", "ON ANGER"),
        ("The Essays", "ON THE SHORTNESS OF LIFE"),
    ]


def test_classifies_apparatus_sections():
    entries = parse_toc(SENECA_TOC)
    apparatus = [e.title for e in entries if e.kind == "apparatus"]
    assert "INTRODUCTION TO SENECA by John W. Basore" in apparatus


def test_latin_texts_kept_as_separate_kind():
    entries = parse_toc(SENECA_TOC)
    assert [e.title for e in entries if e.kind == "latin"] == ["LIST OF LATIN TEXTS"]


def test_work_titles_starting_with_The_are_not_mistaken_for_sections():
    # regressione: Hegel ha opere che iniziano con "The "
    entries = parse_toc(HEGEL_TOC)
    works = [e.title for e in entries if e.kind == "work"]
    assert works == ["The Phenomenology of Spirit", "The Logic of Hegel"]


def test_criticism_is_apparatus_not_work():
    entries = parse_toc(HEGEL_TOC)
    assert [e.title for e in entries if e.kind == "apparatus"] == [
        "On Some Hegelisms by William James"
    ]
