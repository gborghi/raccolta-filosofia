from scripts.extract.dump_heads import HEAD_MARKER, dump_heads
from scripts.extract.sources import SOURCES

DOC = """The Complete Works of

Contents

The Essays

ON ANGER

© Delphi Classics 2014

ON ANGER

Translated by Aubrey Stewart

CONTENTS

Book I.
"""


def test_emits_one_block_per_work_with_marker():
    out = dump_heads(DOC, SOURCES["seneca"], lines_per_work=6)
    assert out.count(HEAD_MARKER) == 1
    assert "ON ANGER" in out


def test_block_carries_the_lines_after_the_header():
    out = dump_heads(DOC, SOURCES["seneca"], lines_per_work=6)
    assert "Translated by Aubrey Stewart" in out
    assert "CONTENTS" in out


def test_apparatus_is_not_dumped():
    doc = DOC.replace("The Essays", "The Biography")
    out = dump_heads(doc, SOURCES["seneca"], lines_per_work=6)
    assert out.count(HEAD_MARKER) == 0
