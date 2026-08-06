from __future__ import annotations

import re
from dataclasses import dataclass

# Vocabolario CHIUSO. Non usare un pattern: "The Phenomenology of Spirit"
# è un'opera di Hegel, non una sezione.
WORK_SECTIONS = frozenset({
    "The Books", "The Novels", "The Plays", "The Tragedies",
    "The Epistles", "The Essays", "The Letters", "The Poetry",
    "The Translations", "The Dialogues", "The Treatises",
})
APPARATUS_SECTIONS = frozenset({
    "The Criticism", "The Biography", "The Biographies",
    "The Autobiography", "The Delphi Classics Catalogue",
})
LATIN_SECTIONS = frozenset({"The Latin Texts", "The Greek Texts"})

ALL_SECTIONS = WORK_SECTIONS | APPARATUS_SECTIONS | LATIN_SECTIONS

# Pubblico: delphi_body lo usa per sapere dove finisce il TOC e iniziare
# a cercare gli header di corpo.
TOC_END = re.compile(r"^(©\s*Delphi Classics|Version\s+\d)", re.IGNORECASE)


@dataclass(frozen=True)
class TocEntry:
    section: str
    title: str
    kind: str  # "work" | "apparatus" | "latin"


_KIND_BY_SECTION = (
    [(s, "work") for s in WORK_SECTIONS]
    + [(s, "apparatus") for s in APPARATUS_SECTIONS]
    + [(s, "latin") for s in LATIN_SECTIONS]
)
_KIND = dict(_KIND_BY_SECTION)


def parse_toc(text: str) -> list[TocEntry]:
    lines = text.split("\n")
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == "Contents")
    except StopIteration:
        return []

    entries: list[TocEntry] = []
    section = ""
    for raw in lines[start + 1:]:
        line = raw.strip()
        if not line:
            continue
        if TOC_END.match(line):
            break
        if line in ALL_SECTIONS:
            section = line
            continue
        if section:
            entries.append(TocEntry(section, line, _KIND[section]))
    return entries
