# tests/extract/test_run.py
from scripts.extract.delphi_toc import parse_toc
from scripts.extract.run import SourceReport, format_report


def test_report_flags_incomplete_source():
    r = SourceReport(key="seneca", toc_publishable=25, extracted=23, missing=["ON LEISURE", "MEDEA"])
    assert r.ok is False
    out = format_report([r])
    assert "seneca" in out
    assert "23/25" in out
    assert "ON LEISURE" in out


def test_report_ok_when_all_located():
    r = SourceReport(key="hume", toc_publishable=12, extracted=12, missing=[])
    assert r.ok is True
    assert "12/12" in format_report([r])


def test_unmarked_work_fails_the_source():
    # confine del blurb ignoto -> non pubblicata -> la fonte non e' OK
    r = SourceReport(key="kant", toc_publishable=16, extracted=15, unmarked=["ON PEACE"])
    assert r.ok is False
    assert "ON PEACE" in format_report([r])


def test_skipped_dividers_do_not_fail_the_source():
    # lucretius: TOC dichiara 6, 2 sono divisori Delphi (skip), 4 pubblicate.
    r = SourceReport(key="lucretius", toc_publishable=6, extracted=4, skipped=2)
    assert r.ok is True
    out = format_report([r])
    assert "4/6" in out
    assert "2" in out


TOC_WITH_LATIN = """Contents

The Essays

ON ANGER

The Latin Texts

DE IRA

© Delphi Classics 2014
"""


def test_latin_entries_count_as_publishable():
    # extract() pubblica sia "work" che "latin" (solo "apparatus" e' escluso).
    # Il conteggio atteso deve misurare la stessa cosa, altrimenti una fonte
    # con una sezione Latin Texts (es. seneca) risulta erroneamente FAIL.
    entries = parse_toc(TOC_WITH_LATIN)
    toc_publishable = sum(1 for e in entries if e.kind in ("work", "latin"))
    assert toc_publishable == 2
