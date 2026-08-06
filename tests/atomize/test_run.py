from pathlib import Path

from scripts.atomize.run import WorkReport, atomize_work, discover_raw_files, main

P = " ".join(["word"] * 900)  # 900 parole


def _write_raw(root: Path, philosopher: str, stem: str, *,
                traduttore: str | None = "J. Translator") -> Path:
    trad_line = f'traduttore: "{traduttore}"' if traduttore else "traduttore: null"
    text = f"""---
title: "{stem.replace('_', ' ')}"
philosopher: "{philosopher}"
lang: "en"
edizione: "Delphi Classics"
{trad_line}
anno_edizione: 2000
pd_year: 1900
source_key: "{philosopher.lower()}"
kind: "work"
---

# {stem.replace('_', ' ')}

CHAPTER I

{P}

CHAPTER II

{P}
"""
    out_dir = root / "Philosophers" / philosopher / "_raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stem}.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_atomize_work_writes_atoms_with_inherited_frontmatter(tmp_path):
    raw = _write_raw(tmp_path, "Testphil", "Sample_Work")
    report = atomize_work(raw, out_root=tmp_path)

    assert isinstance(report, WorkReport)
    assert report.philosopher == "Testphil"
    assert report.atoms == 2

    out_dir = tmp_path / "Philosophers" / "Testphil" / "Atomized" / "Sample_Work"
    files = sorted(out_dir.glob("*.md"))
    assert len(files) == 2
    assert files[0].name == "001_CHAPTER_I.md"
    assert files[1].name == "002_CHAPTER_II.md"

    first = files[0].read_text(encoding="utf-8")
    assert 'philosopher: "Testphil"' in first
    assert 'lang: "en"' in first
    assert 'edizione: "Delphi Classics"' in first
    assert 'traduttore: "J. Translator"' in first
    assert "pd_year: 1900" in first
    assert 'source_key: "testphil"' in first
    assert 'work: "Sample_Work"' in first
    assert "atom_n: 1" in first
    assert 'atom_title: "CHAPTER I"' in first
    assert 'kind: "atom"' in first
    assert "word word word" in first


def test_atomize_work_handles_null_traduttore(tmp_path):
    raw = _write_raw(tmp_path, "Testphil", "No_Translator_Work", traduttore=None)
    atomize_work(raw, out_root=tmp_path)
    out_dir = tmp_path / "Philosophers" / "Testphil" / "Atomized" / "No_Translator_Work"
    first = sorted(out_dir.glob("*.md"))[0].read_text(encoding="utf-8")
    assert "traduttore: null" in first


def test_discover_raw_files_finds_every_work_under_every_philosopher(tmp_path):
    _write_raw(tmp_path, "Alpha", "Work_One")
    _write_raw(tmp_path, "Alpha", "Work_Two")
    _write_raw(tmp_path, "Beta", "Work_Three")
    found = discover_raw_files(tmp_path)
    assert len(found) == 3
    assert all(p.suffix == ".md" for p in found)


def test_main_processes_the_whole_vault_and_returns_zero(tmp_path):
    _write_raw(tmp_path, "Alpha", "Work_One")
    _write_raw(tmp_path, "Beta", "Work_Two")
    code = main(vault_root=tmp_path)
    assert code == 0
    assert (tmp_path / "Philosophers" / "Alpha" / "Atomized" / "Work_One").exists()
    assert (tmp_path / "Philosophers" / "Beta" / "Atomized" / "Work_Two").exists()


def test_long_work_stem_produces_a_60_char_directory_name(tmp_path):
    long_stem = "A" * 90  # slug > 60 chars, no underscores to strip
    raw = _write_raw(tmp_path, "Testphil", long_stem)
    report = atomize_work(raw, out_root=tmp_path)

    atomized = tmp_path / "Philosophers" / "Testphil" / "Atomized"
    dirs = [d.name for d in atomized.iterdir() if d.is_dir()]
    assert len(dirs) == 1
    assert len(dirs[0]) == 60
    assert dirs[0] == long_stem[:60]
    # full title not lost: work field in frontmatter carries the untruncated stem
    first = sorted((atomized / dirs[0]).glob("*.md"))[0].read_text(encoding="utf-8")
    assert f'work: "{long_stem}"' in first
    assert report.work == long_stem


def test_long_atom_title_slug_capped_at_40_chars_with_prefix_intact(tmp_path):
    # CHAPTER heading (matches the structural marker regex) with a long tail
    # so the slugified title exceeds 40 chars.
    long_title = "CHAPTER I ON A VERY LONG AND VERBOSE SUBJECT THAT KEEPS GOING ON AND ON"
    text = f"""---
title: "Long Title Work"
philosopher: "Testphil"
lang: "en"
edizione: "Delphi Classics"
traduttore: null
anno_edizione: 2000
pd_year: 1900
source_key: "testphil"
kind: "work"
---

# Long Title Work

{long_title.replace('_', ' ')}

{P}
"""
    out_dir = tmp_path / "Philosophers" / "Testphil" / "_raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "Long_Title_Work.md"
    raw.write_text(text, encoding="utf-8")

    atomize_work(raw, out_root=tmp_path)
    atom_dir = tmp_path / "Philosophers" / "Testphil" / "Atomized" / "Long_Title_Work"
    files = sorted(atom_dir.glob("*.md"))
    assert len(files) == 1
    name = files[0].name
    assert name.startswith("001_")
    slug_part = name[len("001_"):-len(".md")]
    assert len(slug_part) == 40

    content = files[0].read_text(encoding="utf-8")
    full_title = long_title.replace("_", " ")
    assert f'atom_title: "{full_title}"' in content


def test_two_works_colliding_on_truncated_dir_name_get_distinct_dirs(tmp_path):
    prefix = "B" * 60
    raw1 = _write_raw(tmp_path, "Testphil", prefix + "_first_variant_tail")
    raw2 = _write_raw(tmp_path, "Testphil", prefix + "_second_variant_tail")

    atomize_work(raw1, out_root=tmp_path)
    atomize_work(raw2, out_root=tmp_path)

    atomized = tmp_path / "Philosophers" / "Testphil" / "Atomized"
    dirs = sorted(d.name for d in atomized.iterdir() if d.is_dir())
    assert len(dirs) == 2
    assert dirs[0] != dirs[1]
    assert dirs[0] == prefix[:60]
    assert dirs[1] == prefix[:60] + "_2"
