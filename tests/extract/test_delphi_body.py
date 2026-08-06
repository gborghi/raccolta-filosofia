# tests/extract/test_delphi_body.py
from scripts.extract.delphi_body import (
    body_search_start,
    find_body_line,
    is_toc_occurrence,
    next_nonblank,
)

TITLES = ["ON ANGER", "ON THE SHORTNESS OF LIFE", "ON CLEMENCY"]

# TOC a idx 2, colophon a idx 6, corpo a idx 8.
DOC = [
    "Contents", "",
    "ON ANGER", "",
    "ON THE SHORTNESS OF LIFE", "",
    "© Delphi Classics 2014", "",
    "ON ANGER", "", "", "",
    "Translated by Aubrey Stewart", "",
    "CONTENTS", "", "Book I.",
]


def test_next_nonblank_skips_blank_lines():
    assert next_nonblank(["A", "", "", "B"], 0) == "B"


def test_next_nonblank_empty_at_end():
    assert next_nonblank(["A", "", ""], 0) == ""


def test_toc_occurrence_is_followed_by_another_title():
    assert is_toc_occurrence(DOC, 2, TITLES) is True


def test_body_header_is_not_followed_by_a_title():
    # seguito da "Translated by ...", non da un titolo del TOC
    assert is_toc_occurrence(DOC, 8, TITLES) is False


def test_latin_section_toc_detected_via_suffixed_successor():
    # il TOC dei Testi Latini elenca titoli col suffisso originale
    lines = ["ON ANGER — De Ira", "", "ON THE SHORTNESS OF LIFE — De Brevitate Vitæ", ""]
    assert is_toc_occurrence(lines, 0, TITLES) is True


def test_body_search_start_skips_past_toc_colophon():
    assert body_search_start(DOC) == 7


def test_body_search_start_is_zero_without_colophon():
    assert body_search_start(["ON ANGER", "", "Translated by X"]) == 0


def test_find_body_line_skips_toc_and_locates_header_before_internal_contents():
    # doppia regressione su ON ANGER: l'occorrenza a idx 2 è nel TOC (scartata
    # dal filtro posizionale), e quella a idx 8 è l'header vero benché seguito
    # da un indice interno anziché da prosa.
    assert find_body_line(DOC, "ON ANGER", 7, TITLES) == 8


def test_find_body_line_matches_title_with_original_language_suffix():
    lines = ["ON THE SHORTNESS OF LIFE — De Brevitate Vitæ", "", "Translated by X"]
    assert find_body_line(lines, "ON THE SHORTNESS OF LIFE", 0, TITLES) == 0


def test_find_body_line_respects_start_to_avoid_character_name_collision():
    # regressione AGAMEMNON: il titolo compare come nome di personaggio prima
    lines = ["AGAMEMNON", "", "Speak on.", "", "AGAMEMNON", "", "Translated by X"]
    assert find_body_line(lines, "AGAMEMNON", 4, TITLES) == 4


def test_find_body_line_returns_none_when_absent():
    assert find_body_line(DOC, "NATURAL QUESTIONS", 7, TITLES) is None


from scripts.extract.delphi_body import strip_to_start

BODY = """

Translated by J. B. Baillie

First published in 1807, Phanomenologie des Geistes was described by its author as an exposition of the coming to be of knowledge.

The book consists of a Preface, an Introduction, and six major divisions of varying size and complexity.

CONTENTS

Preface: On Scientific Knowledge
"""


def test_cuts_everything_before_the_marker():
    text, found = strip_to_start(BODY, "CONTENTS")
    assert found is True
    assert text.startswith("CONTENTS")
    assert "Translated by" not in text
    assert "First published in 1807" not in text
    assert "The book consists of" not in text


def test_marker_absent_returns_body_unchanged_and_flags_it():
    text, found = strip_to_start(BODY, "NOSUCHLINE")
    assert found is False
    assert text == BODY.strip()


def test_empty_marker_means_no_blurb_to_cut():
    # opere senza blurb: il testo vero comincia subito
    text, found = strip_to_start(BODY, "")
    assert found is True
    assert text == BODY.strip()


def test_cuts_at_first_occurrence_not_a_later_one():
    body = "blurb line\n\nCONTENTS\n\nreal text\n\nCONTENTS\n"
    text, _ = strip_to_start(body, "CONTENTS")
    assert text.startswith("CONTENTS\n\nreal text")
