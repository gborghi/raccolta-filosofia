from scripts.atomize.headings import contents_block

PROSE = "It is the first letter and the prose runs on at length here for many words indeed, well past two hundred characters, so that nothing mistakes it for an index entry of any kind whatsoever, not even by accident."

LINES = ["CONTENTS", "", "I. On Saving Time", "", "II. On Discursiveness", "",
         "I. On Saving Time", "", PROSE]


def test_returns_entries_and_where_the_index_ends():
    entries, end = contents_block(LINES)
    assert entries == ["I. On Saving Time", "II. On Discursiveness"]
    # regressione: end deve essere la fine dell'INDICE (riga 4), non
    # l'occorrenza nel corpo (riga 6)
    assert end == 4


def test_no_contents_returns_empty():
    assert contents_block(["CHAPTER I", "", PROSE]) == ([], 0)


def test_contents_must_be_near_the_top():
    assert contents_block(["x"] * 45 + ["CONTENTS", "", "I. Thing"]) == ([], 0)


from scripts.atomize.headings import heading_lines

PROSE_A = "First letter prose, long enough past two hundred characters to be unmistakable, running on and on so that no heuristic anywhere could ever mistake this line for an index entry or a heading of any sort."
PROSE_B = "Second letter prose, likewise well past two hundred characters in length, running on at sufficient length that it is plainly prose and nothing else at all, by any measure one might apply."

DOC = ["CONTENTS", "", "I. On Saving Time", "", "II. On Discursiveness", "",
       "I. On Saving Time", "", PROSE_A, "",
       "II. On Discursiveness", "", PROSE_B, "",
       "CHAPTER IV", "", PROSE_A]


def test_locates_contents_entries_in_the_body():
    heads, end = heading_lines(DOC)
    assert heads[6] == "I. On Saving Time"
    assert heads[10] == "II. On Discursiveness"


def test_adds_structural_markers_the_contents_does_not_list():
    heads, _ = heading_lines(DOC)
    assert heads[14] == "CHAPTER IV"


def test_index_entries_themselves_are_not_headings():
    heads, end = heading_lines(DOC)
    assert all(i > end for i in heads)


def test_work_without_contents_still_gets_marker_headings():
    doc = ["CHAPTER I", "", PROSE_A, "", "CHAPTER II", "", PROSE_B]
    heads, end = heading_lines(doc)
    assert sorted(heads.values()) == ["CHAPTER I", "CHAPTER II"]
