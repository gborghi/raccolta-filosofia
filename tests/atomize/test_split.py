from scripts.atomize.split import split_work

P = " ".join(["word"] * 900)   # 900 parole


def test_long_block_is_chunked_to_target():
    body = "CHAPTER I\n\n" + P + "\n\n" + P + "\n\n" + P
    atoms = split_work(body)
    assert len(atoms) >= 2
    assert all(len(a.text.split()) <= 2600 for a in atoms)


def test_paragraphs_are_never_broken_mid_way():
    body = "CHAPTER I\n\n" + P + "\n\n" + P
    for a in split_work(body):
        assert not a.text.strip().endswith("word word word\nword")


def test_headings_become_atom_titles():
    body = "CHAPTER I\n\nshort text\n\nCHAPTER II\n\nother text"
    assert [a.title for a in split_work(body)] == ["CHAPTER I", "CHAPTER II"]


def test_text_before_the_first_heading_is_kept():
    body = "opening words here\n\nCHAPTER I\n\nbody text"
    assert split_work(body)[0].title == "(apertura)"


def test_work_with_no_headings_is_still_chunked():
    # regressione: senza questo un'opera senza intestazioni resta un atomo
    # da 136k parole
    atoms = split_work(P + "\n\n" + P + "\n\n" + P)
    assert len(atoms) >= 2
    assert all(len(a.text.split()) <= 2600 for a in atoms)


def test_atoms_are_numbered_from_one():
    body = "CHAPTER I\n\na\n\nCHAPTER II\n\nb"
    assert [a.n for a in split_work(body)] == [1, 2]
