# tests/extract/test_delphi.py
from scripts.extract.delphi import extract
from scripts.extract.sources import SOURCES

PROSE_A = "The majority of mortals, Paulinus, complain bitterly of the spitefulness of Nature, because we are born for a brief span of life."
PROSE_B = "It is not that we have a short time to live, but that we waste a great deal of it before we truly begin to live at all."

DOC = f"""The Complete Works of

SENECA THE YOUNGER

Contents

The Essays

ON ANGER

ON THE SHORTNESS OF LIFE

The Biography

INTRODUCTION TO SENECA

The Delphi Classics Catalogue

© Delphi Classics 2014

ON ANGER

Translated by John W. Basore

This dialogue on anger, addressed to Novatus, is the fullest surviving ancient treatment of the passion and its remedies.

{PROSE_A}

ON THE SHORTNESS OF LIFE

Translated by John W. Basore

{PROSE_B}

INTRODUCTION TO SENECA

This biographical essay by the translator surveys the life and times of the Stoic philosopher across the reigns of Caligula and Nero.
"""


STARTS = {
    "ON ANGER": {"first_line": PROSE_A, "traduttore": "John W. Basore"},
    "ON THE SHORTNESS OF LIFE": {"first_line": PROSE_B, "traduttore": "John W. Basore"},
}


def test_extracts_only_work_sections():
    result = extract(DOC, SOURCES["seneca"], STARTS)
    assert [w.title for w in result.works] == ["ON ANGER", "ON THE SHORTNESS OF LIFE"]


def test_apparatus_section_is_not_extracted():
    result = extract(DOC, SOURCES["seneca"], STARTS)
    titles = [w.title for w in result.works]
    assert "INTRODUCTION TO SENECA" not in titles


def test_work_text_spans_to_next_work_header():
    result = extract(DOC, SOURCES["seneca"], STARTS)
    on_anger = result.works[0]
    assert PROSE_A in on_anger.text
    assert PROSE_B not in on_anger.text


def test_editorial_blurb_stripped_from_work_text():
    result = extract(DOC, SOURCES["seneca"], STARTS)
    on_anger = result.works[0]
    assert "This dialogue on anger" not in on_anger.text
    assert on_anger.text.startswith(PROSE_A)


def test_translator_comes_from_starts_data():
    result = extract(DOC, SOURCES["seneca"], STARTS)
    assert result.works[0].traduttore == "John W. Basore"


def test_last_work_does_not_bleed_into_apparatus():
    result = extract(DOC, SOURCES["seneca"], STARTS)
    last = result.works[-1]
    assert "biographical essay" not in last.text


def test_missing_reports_unlocated_toc_titles():
    doc = DOC.replace("\nON ANGER\n\nTranslated by John W. Basore\n", "\n")
    result = extract(doc, SOURCES["seneca"], STARTS)
    assert "ON ANGER" in result.missing


def test_work_without_starts_entry_is_unmarked_not_published():
    # non sappiamo dove finisce il blurb -> non si pubblica
    result = extract(DOC, SOURCES["seneca"], {k: v for k, v in STARTS.items()
                                              if k != "ON ANGER"})
    assert "ON ANGER" in result.unmarked
    assert "ON ANGER" not in [w.title for w in result.works]


def test_work_whose_marker_is_absent_from_body_is_unmarked():
    bad = dict(STARTS, **{"ON ANGER": {"first_line": "NOSUCHLINE", "traduttore": None}})
    result = extract(DOC, SOURCES["seneca"], bad)
    assert "ON ANGER" in result.unmarked
    assert "ON ANGER" not in [w.title for w in result.works]


def test_entry_missing_first_line_key_is_unmarked_not_published():
    # CRITICAL 1: chiave "first_line" ASSENTE (non "") -> confine sconosciuto.
    # info.get("first_line", "") degraderebbe verso "nessun blurb, pubblica
    # tutto": per un confine di copyright questo e' fail-open, inaccettabile.
    bad = dict(STARTS, **{"ON ANGER": {"traduttore": None}})
    result = extract(DOC, SOURCES["seneca"], bad)
    assert "ON ANGER" in result.unmarked
    assert "ON ANGER" not in [w.title for w in result.works]


def test_explicit_empty_first_line_still_publishes():
    # "first_line": "" ESPLICITA resta valida: significa "verificato, nessun
    # blurb". Non deve regredire a unmarked per colpa del fix di CRITICAL 1.
    starts = dict(STARTS, **{"ON ANGER": {"first_line": "", "traduttore": "John W. Basore"}})
    result = extract(DOC, SOURCES["seneca"], starts)
    assert "ON ANGER" in [w.title for w in result.works]
    assert "ON ANGER" not in result.unmarked


def test_skipped_only_counts_entries_actually_skipped_in_toc():
    # IMPORTANT 3: una riga "skip" bogus per un titolo assente dal TOC non
    # deve comparire in result.skipped (altrimenti maschera un'opera davvero
    # non pubblicata dietro un conteggio aritmetico).
    bad = dict(STARTS, **{"NO SUCH TITLE": {"skip": True}})
    result = extract(DOC, SOURCES["seneca"], bad)
    assert result.skipped == []


def test_skipped_entry_recorded_in_result():
    starts = dict(STARTS, **{"ON ANGER": {"skip": True}})
    result = extract(DOC, SOURCES["seneca"], starts)
    assert "ON ANGER" in result.skipped
    assert "ON ANGER" not in [w.title for w in result.works]
    assert "ON ANGER" not in result.unmarked


DOC_LATIN = f"""The Complete Works of

SENECA THE YOUNGER

Contents

The Essays

ON ANGER

The Latin Texts

DE IRA

© Delphi Classics 2014

ON ANGER

Translated by John W. Basore

{PROSE_A}
"""


def test_unlocated_latin_entry_is_reported_missing():
    # IMPORTANT 4: un'entry kind=="latin" mai localizzata deve finire in
    # missing tanto quanto kind=="work" -- entrambe vengono pubblicate.
    result = extract(DOC_LATIN, SOURCES["seneca"],
                     {"ON ANGER": {"first_line": PROSE_A, "traduttore": "John W. Basore"}})
    assert "DE IRA" in result.missing


DOC_EMPTY_BODY = """The Complete Works of

SENECA THE YOUNGER

Contents

The Essays

ON ANGER

© Delphi Classics 2014

ON ANGER
"""


def test_empty_body_after_cut_is_unmarked_not_silently_dropped():
    # IMPORTANT 5: `if not clean: continue` faceva sparire l'opera senza
    # segnalazione. verify_starts.py tratta lo stesso caso come fallimento
    # ("testo VUOTO dopo il taglio"): devono concordare.
    starts = {"ON ANGER": {"first_line": "", "traduttore": None}}
    result = extract(DOC_EMPTY_BODY, SOURCES["seneca"], starts)
    assert "ON ANGER" in result.unmarked
    assert "ON ANGER" not in [w.title for w in result.works]
