import pytest
import yaml

from scripts.extract import common
from scripts.extract.common import Work, load_raw, render, slugify, write_work
from scripts.extract.sources import SOURCES, Source


def test_slugify_uppercase_title():
    assert slugify("ON THE SHORTNESS OF LIFE") == "ON_THE_SHORTNESS_OF_LIFE"


def test_slugify_strips_latin_subtitle_and_punctuation():
    assert slugify("ON THE SHORTNESS OF LIFE — De Brevitate Vitæ") == "ON_THE_SHORTNESS_OF_LIFE"
    assert slugify("What is Enlightenment?") == "What_is_Enlightenment"


def test_render_emits_copyright_frontmatter():
    w = Work(title="ON LEISURE", text="Body text here.", kind="work")
    out = render(w, SOURCES["seneca"])
    assert 'title: "ON LEISURE"' in out
    assert 'philosopher: "Seneca"' in out
    assert 'lang: "en"' in out
    assert 'edizione: "Delphi Classics"' in out
    assert "pd_year: 1900" in out
    assert "# ON LEISURE" in out
    assert out.rstrip().endswith("Body text here.")


def test_render_uses_work_translator_over_source_default():
    w = Work(title="ON LEISURE", text="x", kind="work", traduttore="John W. Basore")
    out = render(w, SOURCES["seneca"])
    assert 'traduttore: "John W. Basore"' in out


def test_write_work_creates_raw_path(tmp_path):
    w = Work(title="ON LEISURE", text="x", kind="work")
    p = write_work(w, SOURCES["seneca"], tmp_path)
    assert p == tmp_path / "Philosophers" / "Seneca" / "_raw" / "ON_LEISURE.md"
    assert p.read_text(encoding="utf-8").startswith("---\n")


def _frontmatter_block(out: str) -> str:
    # out is "---\n<frontmatter>\n---\n\n# title\n\n...". Split on the "---"
    # delimiters rather than substring-matching individual keys.
    parts = out.split("---")
    return parts[1]


def test_yaml_escape_survives_double_quote_in_title():
    w = Work(title='ON "LEISURE"', text="x", kind="work")
    out = render(w, SOURCES["seneca"])
    parsed = yaml.safe_load(_frontmatter_block(out))
    assert parsed["title"] == 'ON "LEISURE"'


def test_yaml_escape_survives_backslash_in_title():
    w = Work(title=r"ON \LEISURE\ PATH", text="x", kind="work")
    out = render(w, SOURCES["seneca"])
    parsed = yaml.safe_load(_frontmatter_block(out))
    assert parsed["title"] == r"ON \LEISURE\ PATH"


def test_render_frontmatter_has_all_ten_keys():
    # The key set is exact on purpose: provenance fields are citable, so a field
    # silently disappearing from the frontmatter must fail here. `tomo` is emitted
    # for every work (null unless the edition is multi-volume — Ortega, Aquinas);
    # the hand-rolled renderers in marx_kant_pd.py and aristotle_pd.py write it too.
    w = Work(title="ON LEISURE", text="x", kind="work")
    out = render(w, SOURCES["seneca"])
    parsed = yaml.safe_load(_frontmatter_block(out))
    expected_keys = {
        "title", "philosopher", "lang", "edizione", "traduttore",
        "anno_edizione", "pd_year", "source_key", "kind", "tomo",
    }
    assert expected_keys == set(parsed.keys())


def test_load_raw_raises_when_source_has_no_files():
    ghost = Source("nonesuch", "Nonesuch", "delphi", "en", "X", None, None, 1900)
    with pytest.raises(FileNotFoundError, match="nonesuch"):
        load_raw(ghost)


def test_load_raw_strips_grouptxt_markers(tmp_path, monkeypatch):
    # RAW_ROOT is read once at import time in scripts.extract.common; patching
    # the module attribute directly (rather than re-exporting PHILOSOPHY_RAW_ROOT
    # + reimporting) is the simpler of the two TDD options and load_raw looks
    # up RAW_ROOT as a plain module global at call time, so this is sufficient.
    monkeypatch.setattr(common, "RAW_ROOT", tmp_path)
    src_dir = tmp_path / "markertest"
    src_dir.mkdir()
    (src_dir / "work_part1.txt").write_text(
        "Prima frase reale.\n"
        "===== FINE FILE: Some Book - Parte 06 di 40.txt =====\n"
        "===== INIZIO FILE: Some Book - Parte 07 di 40.txt =====\n"
        "Seconda frase reale.\n",
        encoding="utf-8",
    )
    source = Source("markertest", "MarkerTest", "delphi", "en", "X", None, None, 1900)

    text = load_raw(source)

    assert "INIZIO FILE" not in text
    assert "FINE FILE" not in text
    assert "=====" not in text
    assert "Prima frase reale." in text
    assert "Seconda frase reale." in text
