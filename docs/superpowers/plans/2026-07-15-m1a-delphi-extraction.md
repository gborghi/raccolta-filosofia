# M1a — Estrazione Delphi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estrarre le opere degli 8 filosofi in edizione Delphi Classics dai blob concatenati, un file markdown per opera, testo nudo senza apparato editoriale.

**Architecture:** Un parser TOC ricava la lista ordinata delle opere e le sezioni-apparato da scartare. Un localizzatore trova l'header di ogni opera nel corpo discriminandolo dalle occorrenze nel TOC (una voce di TOC è seguita da righe corte; un header di corpo è seguito da prosa). Le opere si estraggono come span fra header consecutivi, con lo strip del blurb editoriale Delphi in testa.

**Tech Stack:** Python 3.12, `pytest`, stdlib only (no deps esterne).

## Global Constraints

- **Interprete Python:** `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe`. `python`/`python3` in Bash è uno stub rotto del Windows Store — non usarli mai.
- **Sorgente:** `E:/giovanni/Dropbox/remotedir/libri/notebooklm/<key>/*_partN.txt`. I file `Parte NN di 40` sono duplicati — ignorarli.
- **Destinazione:** `VaultPhilosophy/Philosophers/<Nome>/_raw/<SLUG>.md`, un file per opera.
- **Apparato editoriale non pubblicato:** sezioni `The Criticism`, `The Biography`, `The Biographies`, `The Autobiography`, `The Delphi Classics Catalogue`, e i blurb Delphi in testa a ogni opera.
- **Frontmatter obbligatorio da subito:** `title`, `philosopher`, `lang`, `edizione`, `traduttore`, `anno_edizione`, `pd_year`, `source_key`, `kind`. La guardia copyright di M6 leggerà questi campi; ricostruirli dopo significa riaprire 13 corpora.
- **Dropbox:** l'albero è dentro Dropbox. Non creare `node_modules/`/`.venv/` qui senza marcarli `com.dropbox.ignored`.
- **Mai Gemini.** Nessun backend non-Claude.
- Working dir: `E:\giovanni\Dropbox\insegnamento\Wiligelmo\SubjectBrain\Philosophy`

## File Structure

| File | Responsabilità |
|---|---|
| `scripts/extract/sources.py` | Registry: metadati per fonte (edizione, lingua, pd_year, adapter, glob) |
| `scripts/extract/common.py` | `Work` dataclass, slug, emissione frontmatter+file |
| `scripts/extract/delphi_toc.py` | Parsing del TOC → voci ordinate, classificate opera/apparato |
| `scripts/extract/delphi_body.py` | Localizzazione header nel corpo, discriminazione TOC/corpo |
| `scripts/extract/delphi.py` | Orchestrazione: span, strip blurb, → `Work[]` |
| `scripts/extract/run.py` | CLI + report di verifica |
| `tests/extract/test_*.py` | Test per modulo |

Split per responsabilità: il TOC e il corpo sono due problemi di parsing indipendenti con modi di fallire diversi, e vanno testati separatamente.

---

### Task 1: Scaffolding e registry delle fonti

**Files:**
- Create: `scripts/extract/__init__.py` (vuoto)
- Create: `scripts/extract/sources.py`
- Create: `tests/__init__.py` (vuoto), `tests/extract/__init__.py` (vuoto)
- Test: `tests/extract/test_sources.py`

**Interfaces:**
- Produces: `Source` dataclass (campi sotto); `SOURCES: dict[str, Source]`; `delphi_sources() -> list[Source]`

- [ ] **Step 1: Write the failing test**

```python
# tests/extract/test_sources.py
from scripts.extract.sources import SOURCES, delphi_sources


def test_eight_delphi_sources():
    keys = {s.key for s in delphi_sources()}
    assert keys == {
        "seneca", "pascal", "marx", "hegel",
        "kant", "hume", "locke", "lucretius",
    }


def test_every_source_carries_copyright_metadata():
    for s in SOURCES.values():
        assert s.lang, f"{s.key}: lang mancante"
        assert s.edizione, f"{s.key}: edizione mancante"
        assert s.pd_year is not None, f"{s.key}: pd_year mancante"


def test_every_source_is_public_domain():
    # Nessuna fonte protetta: risolto risalendo agli originali + strip apparati.
    # Se questo test fallisce, il sito sta per pubblicare qualcosa che non può.
    for s in SOURCES.values():
        assert s.pd_year <= 2026, f"{s.key}: pd_year {s.pd_year} — non pubblicabile"


def test_nietzsche_is_german_original_not_translation():
    # regressione: la trad. Newton Compton 2012 era protetta; la Levy inglese
    # è PD solo a metà (Ludovici † 1971 -> 2042). L'originale tedesco no.
    n = SOURCES["nietzsche"]
    assert n.lang == "de"
    assert n.traduttore is None


def test_davila_excluded():
    # unica fonte residua protetta, nessun originale accessibile
    assert "davila" not in SOURCES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.extract.sources'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/extract/sources.py
"""Registry delle fonti. pd_year = anno in cui l'EDIZIONE entra in pubblico dominio,
non l'autore: per un testo PD è la traduzione/apparato a essere protetto."""
from __future__ import annotations

from dataclasses import dataclass

RAW_ROOT = r"E:/giovanni/Dropbox/remotedir/libri/notebooklm"


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    adapter: str
    lang: str
    edizione: str
    traduttore: str | None
    anno_edizione: int | None
    pd_year: int
    glob: str = "*_part*.txt"


def _delphi(key: str, name: str, anno: int) -> Source:
    return Source(
        key=key, name=name, adapter="delphi", lang="en",
        edizione="Delphi Classics", traduttore=None,
        anno_edizione=anno, pd_year=1900,
    )


SOURCES: dict[str, Source] = {
    s.key: s
    for s in [
        # Delphi: traduzioni ottocentesche PD. pd_year=1900 = già PD.
        _delphi("seneca", "Seneca", 2014),
        _delphi("pascal", "Pascal", 2000),
        _delphi("marx", "Marx", 2000),
        _delphi("hegel", "Hegel", 2000),
        _delphi("kant", "Kant", 2000),
        _delphi("hume", "Hume", 2000),
        _delphi("locke", "Locke", 2000),
        _delphi("lucretius", "Lucretius", 2000),
        # Non-Delphi: adapter bespoke, piano successivo.
        Source("cartesio", "Descartes", "cartesio", "en",
               "OPU", None, 2019, 1900),
        Source("rousseau", "Rousseau", "rousseau", "fr",
               "Arvensa Editions", None, None, 1900),
        # Originale tedesco: Nietzsche † 1900 -> PD dal 1971, nessun traduttore
        # di mezzo. Anaconda dichiara "Alle Rechte vorbehalten" ma è boilerplate
        # su testo PD; §70 UrhG richiede lavoro critico che una ristampa non ha.
        Source("nietzsche", "Nietzsche", "nietzsche", "de",
               "Anaconda Verlag", None, 2013, 1971, glob="*.epub"),
        Source("ortega", "Ortega y Gasset", "ortega", "es",
               "Obras completas — Fundación Ortega y Gasset", None, None, 2026),
    ]
}
# Dávila: escluso. Traduzioni italiane Krisis protette (~2065), nessun
# originale accessibile. Analogo di EXCLUDE_AUTHORS (Hemingway) in English.


def delphi_sources() -> list[Source]:
    return [s for s in SOURCES.values() if s.adapter == "delphi"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_sources.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/extract/ tests/
git commit -m "feat(extract): source registry with edition copyright metadata"
```

---

### Task 2: Work dataclass ed emissione file

**Files:**
- Create: `scripts/extract/common.py`
- Test: `tests/extract/test_common.py`

**Interfaces:**
- Consumes: `Source` da Task 1
- Produces: `Work(title, text, kind)` dataclass; `slugify(s) -> str`; `render(work, source) -> str`; `write_work(work, source, vault_root) -> Path`

- [ ] **Step 1: Write the failing test**

```python
# tests/extract/test_common.py
from scripts.extract.common import Work, render, slugify, write_work
from scripts.extract.sources import SOURCES


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_common.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.extract.common'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/extract/common.py
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .sources import Source


@dataclass
class Work:
    title: str
    text: str
    kind: str = "work"          # "work" | "latin"
    traduttore: str | None = None


def slugify(s: str) -> str:
    # Il corpo Delphi aggiunge il titolo originale dopo un em-dash: tagliarlo.
    s = re.split(r"\s+[—–]\s+", s)[0]
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return re.sub(r"\s+", "_", s.strip())


def _yaml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def render(work: Work, source: Source) -> str:
    traduttore = work.traduttore or source.traduttore
    lines = [
        "---",
        f'title: "{_yaml_escape(work.title)}"',
        f'philosopher: "{_yaml_escape(source.name)}"',
        f'lang: "{source.lang}"',
        f'edizione: "{_yaml_escape(source.edizione)}"',
        f'traduttore: "{_yaml_escape(traduttore)}"' if traduttore else "traduttore: null",
        f"anno_edizione: {source.anno_edizione}" if source.anno_edizione else "anno_edizione: null",
        f"pd_year: {source.pd_year}",
        f'source_key: "{source.key}"',
        f'kind: "{work.kind}"',
        "---",
        "",
        f"# {work.title}",
        "",
        work.text.strip(),
        "",
    ]
    return "\n".join(lines)


def write_work(work: Work, source: Source, vault_root: Path) -> Path:
    out_dir = Path(vault_root) / "Philosophers" / source.name / "_raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slugify(work.title)}.md"
    path.write_text(render(work, source), encoding="utf-8")
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_common.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/extract/common.py tests/extract/test_common.py
git commit -m "feat(extract): Work model and frontmatter rendering"
```

---

### Task 3: Parser del TOC Delphi

**Files:**
- Create: `scripts/extract/delphi_toc.py`
- Test: `tests/extract/test_delphi_toc.py`

**Interfaces:**
- Produces: `TocEntry(section, title, kind)` dataclass; `parse_toc(text) -> list[TocEntry]`; costanti `WORK_SECTIONS`, `APPARATUS_SECTIONS`, `LATIN_SECTIONS`

**Perché serve un vocabolario e non un pattern:** il TOC di Hegel contiene `The Phenomenology of Spirit` e `The Logic of Hegel` — sono **opere** che iniziano con "The ". Una regex `^The ` cancellerebbe metà Hegel. Le sezioni sono un insieme chiuso e vanno elencate.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_delphi_toc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.extract.delphi_toc'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/extract/delphi_toc.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_delphi_toc.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/extract/delphi_toc.py tests/extract/test_delphi_toc.py
git commit -m "feat(extract): Delphi TOC parser with closed section vocabulary"
```

---

### Task 4: Discriminazione TOC/corpo

**Files:**
- Create: `scripts/extract/delphi_body.py`
- Test: `tests/extract/test_delphi_body.py`

**Interfaces:**
- Consumes: `TOC_END` da `delphi_toc` (Task 3)
- Produces: `PROSE_MIN_LEN = 100`; `LOOKAHEAD = 20`; `body_search_start(lines) -> int`; `next_nonblank(lines, i, window=8) -> str`; `is_toc_occurrence(lines, i, titles) -> bool`; `find_body_line(lines, title, start, titles) -> int | None`

**Il problema:** ogni titolo compare più volte — TOC principale, TOC di sezione latina, header nel corpo, e persino come **nome di personaggio** dentro un'altra opera. Nel corpo può avere un suffisso (`ON THE SHORTNESS OF LIFE — De Brevitate Vitæ`).

**Design validato sui file veri prima della stesura. Tre filtri:**

1. **Posizionale** — `body_search_start` salta il blocco TOC, che finisce col colophon (`TOC_END`). Deterministico.
2. **Successore** — `is_toc_occurrence`: la riga non-vuota dopo una voce di TOC è **un altro titolo del TOC**; quella dopo un header di corpo no (è `Translated by …`, o `CONTENTS`, o prosa). Distingue il corpo dal TOC dei Testi Latini, che ricompare a metà file.
3. **Ordine** — la ricerca procede in ordine di TOC, ognuna dopo la precedente (implementato in Task 6).

**Perché NON si usa un'euristica sulla prosa.** L'avevo pianificata ("header di corpo = prosa entro 20 righe") ed è sbagliata: `ON ANGER` a idx 11728 in Seneca è l'header vero ma è seguito da `Translated by Aubrey Stewart` e da un **indice interno all'opera** (`CONTENTS / Book I. / I. / II. …`) — la prosa arriva decine di righe dopo, fuori finestra. Falso negativo. Un indice interno può essere lungo a piacere: allargare la finestra non risolve.

**Perché serve l'ordine.** Senza, `AGAMEMNON` viene localizzato a idx 1049 e `OEDIPUS` a 1698 — **dentro** `THE TROJAN WOMEN` e `THE PHOENICIAN WOMEN`: sono nomi di personaggi nelle battute delle tragedie. Produrrebbe span sovrapposti in silenzio. Il TOC dichiara un ordine, e l'ordine lo risolve.

Verificato: **116/116 opere localizzate** su tutte e 8 le fonti (seneca 25, kant 16, hume 12, locke 18, lucretius 6, pascal 12, hegel 8, marx 19).

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_delphi_body.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.extract.delphi_body'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/extract/delphi_body.py
from __future__ import annotations

import re

from .delphi_toc import TOC_END

# Una voce di TOC è corta. Un paragrafo di prosa no. Soglia dai dati reali:
# i titoli Delphi più lunghi stanno sotto i 90 caratteri.
PROSE_MIN_LEN = 100
LOOKAHEAD = 20


def body_search_start(lines: list[str]) -> int:
    """Prima riga dopo il blocco TOC — dove inizia il corpo.

    Filtro posizionale, deterministico: evita di dipendere dalla distanza
    fra TOC e corpo.
    """
    for i, ln in enumerate(lines):
        if TOC_END.match(ln.strip()):
            return i + 1
    return 0


def next_nonblank(lines: list[str], i: int, window: int = 8) -> str:
    """Prima riga non vuota dopo `i`, o "" se non c'è entro `window`."""
    for j in range(i + 1, min(i + 1 + window, len(lines))):
        s = lines[j].strip()
        if s:
            return s
    return ""


def _matches(line: str, title: str) -> bool:
    line = line.strip()
    if line == title:
        return True
    # Il corpo e il TOC latino aggiungono l'originale: "TITLE — De Ira"
    return bool(re.match(rf"^{re.escape(title)}\s+[—–]\s+\S", line))


def is_toc_occurrence(lines: list[str], i: int, titles: list[str]) -> bool:
    """True se l'occorrenza a `i` sta dentro un elenco, non in testa a un'opera.

    Discriminatore: dopo una voce di TOC viene un ALTRO titolo del TOC;
    dopo un header di corpo viene `Translated by …`, un indice interno, o prosa.
    """
    successor = next_nonblank(lines, i)
    return any(_matches(successor, t) for t in titles)


def find_body_line(
    lines: list[str], title: str, start: int, titles: list[str]
) -> int | None:
    """Indice dell'header di corpo per `title` cercando da `start`, o None.

    `start` deve avanzare in ordine di TOC: senza, un titolo che è anche nome
    di personaggio (AGAMEMNON, OEDIPUS) viene agganciato dentro l'opera
    precedente.
    """
    for i in range(start, len(lines)):
        if _matches(lines[i], title) and not is_toc_occurrence(lines, i, titles):
            return i
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_delphi_body.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/extract/delphi_body.py tests/extract/test_delphi_body.py
git commit -m "feat(extract): discriminate Delphi body headers from TOC entries"
```

---

### Task 5: Confini del testo vero via passata LLM offline

> **Questo task sostituisce un design fallito.** La prima versione cercava di
> togliere il blurb con una regola (`Translated by` + primo paragrafo lungo).
> Verificata sui file veri: **42/116 opere non hanno traduttore** (Hume, Locke e
> Marx scrivevano in inglese) e la funzione restituiva il corpo intatto; le altre
> 74 hanno 0–4 paragrafi di blurb e ne toglieva uno. I test passavano perché la
> fixture era inventata. `strip_front_matter_blurb` (commit `1d5274c`) va sostituita.

**Files:**
- Create: `scripts/extract/dump_heads.py` (deterministico, nessun LLM — estrae le teste da leggere)
- Create: `data/heads/<source_key>.md` (input della passata, rigenerabile)
- Modify: `scripts/extract/common.py` (aggiunge `load_raw`)
- Modify: `scripts/extract/delphi_body.py` (rimuove `strip_front_matter_blurb`, aggiunge `strip_to_start`)
- Modify: `tests/extract/test_delphi_body.py` (rimuove i 3 test del blurb, aggiunge quelli di `strip_to_start`)
- Test: `tests/extract/test_dump_heads.py`

**Interfaces:**
- Consumes: `parse_toc` (Task 3); `body_search_start`, `find_body_line` (Task 4); `Source`, `RAW_ROOT`, `delphi_sources` (Task 1)
- Produces: `load_raw(source) -> str` (in `common.py`); `HEAD_MARKER`; `dump_heads(text, source, lines_per_work=45) -> str`; `strip_to_start(body, first_line) -> tuple[str, bool]`

**`load_raw` va in `common.py`, non in `delphi.py`.** Non ha nulla di specifico a Delphi — fa glob su `RAW_ROOT/<key>/<glob>` e concatena — e ogni adapter futuro (cartesio, rousseau, ortega, nietzsche) ne ha bisogno. Metterlo in `delphi.py` costringerebbe `dump_heads` a importare da un modulo che a questo punto del piano non esiste ancora.

**Perché una passata LLM e non una regola.** Riconoscere la voce editoriale Delphi non è pattern matching, è giudizio. I dati veri:

| caso | forma |
|---|---|
| `hume/A TREATISE OF HUMAN NATURE` | sottotitolo, **3 paragrafi lunghi = blurb**, `The first edition's title page`, `CONTENTS` |
| `hume/AN ABSTRACT OF A BOOK…` | `CONTENTS`, `PREFACE.`, **4 paragrafi lunghi = prefazione VERA di Hume** |
| `pascal/Essay on Conics` | traduttore, `CONTENTS`, …, blurb **dopo** il contents |

Gli stessi paragrafi lunghi in testa sono blurb in un caso e testo d'autore nell'altro. Nessuna regola posizionale li distingue; leggerli sì.

**La passata gira UNA VOLTA e la fanno i subagent della sessione Claude Code — non l'API.** Nessuna dipendenza `anthropic`, nessuna API key, nessun costo metered: l'abbonamento copre già questo lavoro. Il flusso:

1. `dump_heads.py` (deterministico) scrive le prime ~45 righe di ogni opera localizzata in `data/heads/<source_key>.md`, con un marker per opera.
2. Un subagent per fonte legge il file e produce le voci di `data/work_starts.json`.
3. `data/work_starts.json` viene committato. **Da qui in poi nessun LLM è coinvolto**: build e test leggono il JSON.

Se una fonte cambia, si rigenerano le teste e si ripassa solo quella.

**Mai Gemini né alcun backend non-Claude**, qui come ovunque nel progetto.

- [ ] **Step 1: Rimuovere il design fallito**

Elimina da `scripts/extract/delphi_body.py` la funzione `strip_front_matter_blurb` e la regex `_TRANSLATED_BY`. Elimina da `tests/extract/test_delphi_body.py` i suoi 3 test (`test_captures_translator`, `test_strips_translator_and_editorial_blurb`, `test_no_blurb_leaves_text_untouched`).

**Non toccare** `find_body_line`, `is_toc_occurrence`, `body_search_start`, `next_nonblank`: Task 4 è validato (116/116 su dati veri). `PROSE_MIN_LEN` e `LOOKAHEAD` restano — `dump_heads` li usa.

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_delphi_body.py -v`
Expected: PASS (11 passed — solo quelli di Task 4)

- [ ] **Step 2: Write the failing test per `strip_to_start`**

```python
# append a tests/extract/test_delphi_body.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_delphi_body.py -v`
Expected: FAIL — `ImportError: cannot import name 'strip_to_start'`

- [ ] **Step 4: Implementare `strip_to_start`**

```python
# append a scripts/extract/delphi_body.py

def strip_to_start(body: str, first_line: str) -> tuple[str, bool]:
    """Taglia tutto ciò che precede `first_line` — il blurb editoriale Delphi.

    `first_line` viene da data/work_starts.json ed è la prima riga del testo
    d'autore. Stringa vuota = nessun blurb, il testo comincia subito.
    Ritorna (testo, trovato); trovato=False significa marker non presente:
    il chiamante deve segnalarlo, non pubblicare a caso.
    """
    body = body.strip()
    if not first_line:
        return body, True
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if line.strip() == first_line:
            return "\n".join(lines[i:]).strip(), True
    return body, False
```

- [ ] **Step 5: Run test to verify it passes**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_delphi_body.py -v`
Expected: PASS (15 passed — 11 di Task 4 + 4 di questo)

- [ ] **Step 5b: Spostare `load_raw` in `common.py`**

Aggiungi a `scripts/extract/common.py` (serve a `dump_heads` e, poi, a ogni adapter):

```python
# in testa a common.py, accanto agli altri import
import glob

# e in fondo al file:
def load_raw(source: Source) -> str:
    """Concatena i blob della fonte. Generico: non è specifico a Delphi."""
    pattern = str(Path(RAW_ROOT) / source.key / source.glob)
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"nessun file per {source.key}: {pattern}")
    return "\n".join(
        Path(p).read_text(encoding="utf-8", errors="replace") for p in paths
    )
```

L'import da aggiornare in cima: `from .sources import RAW_ROOT, Source`.

Test da aggiungere in `tests/extract/test_common.py`:

```python
import pytest
from scripts.extract.common import load_raw
from scripts.extract.sources import Source


def test_load_raw_raises_when_source_has_no_files():
    ghost = Source("nonesuch", "Nonesuch", "delphi", "en", "X", None, None, 1900)
    with pytest.raises(FileNotFoundError, match="nonesuch"):
        load_raw(ghost)
```

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_common.py -v`
Expected: PASS (9 passed — 8 esistenti + questo)

- [ ] **Step 6: Write the failing test per `dump_heads`**

```python
# tests/extract/test_dump_heads.py
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
```

- [ ] **Step 7: Run test to verify it fails**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_dump_heads.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.extract.dump_heads'`

- [ ] **Step 8: Implementare `dump_heads`**

```python
# scripts/extract/dump_heads.py
"""Estrae le teste delle opere per la passata di lettura.

Deterministico: nessun LLM qui. L'output di questo script è ciò che i subagent
della sessione Claude Code leggono per produrre data/work_starts.json.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .common import load_raw
from .delphi_body import body_search_start, find_body_line
from .delphi_toc import parse_toc
from .sources import Source, delphi_sources

HEAD_MARKER = "===== OPERA:"
HEADS_DIR = Path(__file__).resolve().parents[2] / "data" / "heads"


def dump_heads(text: str, source: Source, lines_per_work: int = 45) -> str:
    lines = text.split("\n")
    entries = parse_toc(text)
    titles = [e.title for e in entries]
    out: list[str] = []
    pos = body_search_start(lines)
    for e in entries:
        idx = find_body_line(lines, e.title, pos, titles)
        if idx is None:
            continue
        pos = idx + 1
        if e.kind != "work":
            continue
        head = lines[idx + 1: idx + 1 + lines_per_work]
        out.append(f"{HEAD_MARKER} {e.title}")
        out.extend(head)
        out.append("")
    return "\n".join(out)


def main() -> int:
    HEADS_DIR.mkdir(parents=True, exist_ok=True)
    for s in delphi_sources():
        text = load_raw(s)
        path = HEADS_DIR / f"{s.key}.md"
        path.write_text(dump_heads(text, s), encoding="utf-8")
        print(f"{s.key}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 9: Run test to verify it passes**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_dump_heads.py -v`
Expected: PASS (3 passed)

- [ ] **Step 10: Commit**

```bash
git add scripts/extract/dump_heads.py scripts/extract/delphi_body.py tests/extract/
git commit -m "feat(extract): dump work heads for boundary pass, replace blurb heuristic with strip_to_start"
```

**Nota:** `dump_heads.py` importa `load_raw` da `common.py` (aggiunto allo Step 5b), non da `delphi.py` — che a questo punto del piano non esiste ancora. Non anticipare Task 6.

---

### Passata di lettura (esegue il controller, non un implementer)

Fra Task 5 e Task 6. Non è un task del piano: è lavoro di sessione.

1. `python -m scripts.extract.dump_heads` → `data/heads/*.md`
2. Un subagent per fonte legge `data/heads/<key>.md` e, per ogni blocco `===== OPERA:`, decide dove comincia il testo d'autore — distinguendo il **blurb editoriale Delphi** (voce del curatore: "First published in…", "The book consists of…") dal **testo dell'autore**. Emette `{"first_line": "...", "traduttore": "..."}` per opera; `first_line: ""` se non c'è blurb.
3. Merge in `data/work_starts.json`, committato.
4. Verifica: `data/work_starts.json` copre tutte e 116 le opere; ogni `first_line` non vuota esiste davvero nel corpo (`strip_to_start` ritorna `trovato=True`).

**Solo Claude. Mai Gemini né altri backend.**

---

### Task 6: Adapter Delphi end-to-end

**Files:**
- Create: `scripts/extract/delphi.py`
- Test: `tests/extract/test_delphi.py`

**Interfaces:**
- Consumes: `parse_toc`, `TocEntry` (Task 3); `body_search_start`, `find_body_line` (Task 4); `strip_to_start` (Task 5); `Work`, `load_raw` (Task 2/5); `Source` (Task 1)
- Produces: `ExtractResult(works, missing, unmarked)` dataclass; `extract(text, source, starts) -> ExtractResult`

`starts` è la sezione di `data/work_starts.json` per questa fonte: `{titolo: {"first_line": str, "traduttore": str | None}}`. Un titolo assente, o un `first_line` non trovato nel corpo, finisce in `unmarked` e **non viene pubblicato**: se non sappiamo dove finisce il blurb editoriale, non tiriamo a indovinare.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_delphi.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.extract.delphi'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/extract/delphi.py
from __future__ import annotations

from dataclasses import dataclass, field

from .common import Work
from .delphi_body import body_search_start, find_body_line, strip_to_start
from .delphi_toc import TocEntry, parse_toc
from .sources import Source


@dataclass
class ExtractResult:
    works: list[Work] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unmarked: list[str] = field(default_factory=list)


def extract(text: str, source: Source, starts: dict[str, dict]) -> ExtractResult:
    entries = parse_toc(text)
    lines = text.split("\n")
    titles = [e.title for e in entries]

    # Localizza OGNI voce (anche apparato): serve come confine di fine per l'opera
    # che la precede, altrimenti l'ultima opera assorbe la biografia.
    # Ricerca ORDINATA: `pos` avanza. Senza, AGAMEMNON/OEDIPUS vengono agganciati
    # come nomi di personaggio dentro le tragedie precedenti.
    located: list[tuple[int, TocEntry]] = []
    missing: list[str] = []
    pos = body_search_start(lines)
    for e in entries:
        idx = find_body_line(lines, e.title, pos, titles)
        if idx is None:
            if e.kind == "work":
                missing.append(e.title)
            continue
        located.append((idx, e))
        pos = idx + 1

    works: list[Work] = []
    unmarked: list[str] = []
    for n, (idx, entry) in enumerate(located):
        if entry.kind == "apparatus":
            continue
        end = located[n + 1][0] if n + 1 < len(located) else len(lines)
        body = "\n".join(lines[idx + 1: end])

        # data/work_starts.json dice dove finisce il blurb editoriale Delphi
        # e comincia il testo d'autore. Assente = non lo sappiamo: si segnala,
        # non si pubblica a caso.
        info = starts.get(entry.title)
        if info is None:
            unmarked.append(entry.title)
            continue
        clean, found = strip_to_start(body, info.get("first_line", ""))
        if not found:
            unmarked.append(entry.title)
            continue
        if not clean:
            continue
        works.append(Work(title=entry.title, text=clean, kind=entry.kind,
                          traduttore=info.get("traduttore")))

    return ExtractResult(works=works, missing=missing, unmarked=unmarked)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_delphi.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/extract/delphi.py tests/extract/test_delphi.py
git commit -m "feat(extract): Delphi end-to-end adapter with apparatus boundaries"
```

---

### Task 7: CLI e report di verifica

**Files:**
- Create: `scripts/extract/run.py`
- Test: `tests/extract/test_run.py`

**Interfaces:**
- Consumes: `delphi_sources` (Task 1), `write_work` (Task 2), `load_raw`/`extract` (Task 6)
- Produces: `SourceReport(key, toc_works, extracted, missing)`; `run_source(source, vault_root) -> SourceReport`; `main() -> int`

**Verifica:** il TOC *è* il conteggio atteso — non serve un numero hardcoded. Ogni titolo-opera del TOC deve essere localizzato nel corpo. Un titolo non localizzato è un fallimento da indagare, non da ignorare.

- [ ] **Step 1: Write the failing test**

```python
# tests/extract/test_run.py
from scripts.extract.run import SourceReport, format_report


def test_report_flags_incomplete_source():
    r = SourceReport(key="seneca", toc_works=25, extracted=23, missing=["ON LEISURE", "MEDEA"])
    assert r.ok is False
    out = format_report([r])
    assert "seneca" in out
    assert "23/25" in out
    assert "ON LEISURE" in out


def test_report_ok_when_all_located():
    r = SourceReport(key="hume", toc_works=12, extracted=12, missing=[])
    assert r.ok is True
    assert "12/12" in format_report([r])


def test_unmarked_work_fails_the_source():
    # confine del blurb ignoto -> non pubblicata -> la fonte non e' OK
    r = SourceReport(key="kant", toc_works=16, extracted=15, unmarked=["ON PEACE"])
    assert r.ok is False
    assert "ON PEACE" in format_report([r])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.extract.run'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/extract/run.py
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .common import load_raw, write_work
from .delphi import extract
from .delphi_toc import parse_toc
from .sources import Source, delphi_sources

VAULT_ROOT = Path(__file__).resolve().parents[2] / "VaultPhilosophy"
STARTS_PATH = Path(__file__).resolve().parents[2] / "data" / "work_starts.json"


@dataclass
class SourceReport:
    key: str
    toc_works: int
    extracted: int
    missing: list[str] = field(default_factory=list)
    unmarked: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (not self.missing and not self.unmarked
                and self.extracted == self.toc_works)


def load_starts(path: Path = STARTS_PATH) -> dict[str, dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_source(source: Source, starts: dict[str, dict],
               vault_root: Path = VAULT_ROOT) -> SourceReport:
    text = load_raw(source)
    toc_works = sum(1 for e in parse_toc(text) if e.kind == "work")
    result = extract(text, source, starts.get(source.key, {}))
    for w in result.works:
        write_work(w, source, vault_root)
    return SourceReport(source.key, toc_works, len(result.works),
                        result.missing, result.unmarked)


def format_report(reports: list[SourceReport]) -> str:
    lines = []
    for r in reports:
        mark = "OK  " if r.ok else "FAIL"
        lines.append(f"{mark} {r.key:12} {r.extracted}/{r.toc_works} opere")
        for t in r.missing:
            lines.append(f"       non localizzata: {t}")
        for t in r.unmarked:
            lines.append(f"       confine ignoto (non pubblicata): {t}")
    return "\n".join(lines)


def main() -> int:
    starts = load_starts()
    reports = [run_source(s, starts) for s in delphi_sources()]
    print(format_report(reports))
    return 0 if all(r.ok for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/extract/test_run.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full suite**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/ -v`
Expected: PASS (38 passed — 5 sources, 5 common, 5 toc, 14 body, 7 delphi, 2 run)

- [ ] **Step 6: Commit**

```bash
git add scripts/extract/run.py tests/extract/test_run.py
git commit -m "feat(extract): CLI runner with per-source TOC coverage report"
```

---

### Task 8: Run reale sulle 8 fonti e triage

**Files:**
- Create: `docs/superpowers/notes/2026-07-15-m1a-extraction-report.md`

**Interfaces:**
- Consumes: `main()` (Task 7)

Questo task è il punto in cui il rischio si materializza. Le 7 task precedenti girano su fixture; questa gira sui 60MB veri.

- [ ] **Step 1: Fermare la sync Dropbox**

Il run scrive centinaia di file dentro Dropbox. Metti in pausa la sync dalla tray icon prima di procedere.

- [ ] **Step 2: Eseguire l'estrazione**

Run: `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe -m scripts.extract.run`

Expected: `OK` su tutte e 8, **116 opere in totale**. Il design è stato validato sui file veri prima della stesura del piano, quindi questi numeri sono un bersaglio, non una stima:

| fonte | opere attese |
|---|---|
| seneca | 25 |
| kant | 16 |
| hume | 12 |
| locke | 18 |
| lucretius | 6 |
| pascal | 12 |
| hegel | 8 |
| marx | 19 |

Uno scostamento significa che l'implementazione diverge dal design validato — non che la fonte è strana.

- [ ] **Step 3: Registrare il risultato**

Scrivi `docs/superpowers/notes/2026-07-15-m1a-extraction-report.md` con l'output verbatim del report, e per ogni `FAIL` una riga di diagnosi: il titolo non localizzato esiste nel corpo con grafia diversa? È un'opera senza testo (solo elencata)? Il TOC ha una sezione non nel vocabolario?

- [ ] **Step 4: Ispezione a campione (obbligatoria)**

Non fidarti del conteggio. Apri tre file e leggili:

```bash
head -40 VaultPhilosophy/Philosophers/Seneca/_raw/ON_THE_SHORTNESS_OF_LIFE.md
head -40 VaultPhilosophy/Philosophers/Hegel/_raw/The_Phenomenology_of_Spirit.md
head -40 VaultPhilosophy/Philosophers/Kant/_raw/CRITIQUE_OF_PURE_REASON.md
```

Verifica su ognuno: il frontmatter è completo; il corpo inizia col testo vero e non con un blurb Delphi; non c'è coda di apparato in fondo (`tail -20`).

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/notes/
git commit -m "docs: M1a extraction report across 8 Delphi sources"
```

**Nota:** `VaultPhilosophy/Philosophers/*/_raw/` **non** va committato in questo repo se supera dimensioni ragionevoli — decidere con l'utente prima di `git add` sul vault.

---

## Definition of Done

- `pytest tests/ -v` verde.
- `python -m scripts.extract.run` esce 0, oppure ogni `FAIL` è diagnosticato nel report con una causa nota.
- Ogni opera estratta ha frontmatter completo (`pd_year`, `edizione`, `lang` popolati).
- Ispezione a campione su 3 opere di 3 filosofi diversi: nessun blurb Delphi in testa, nessuna coda di apparato.

## Fuori scope (piano successivo)

Adapter bespoke: `cartesio.py`, `rousseau.py`, `nietzsche.py` (epub, TOC NCX — struttura diversa dai .txt), `ortega.py`, `aquinas.py` (epub). Saranno informati da ciò che impariamo qui — in particolare se la regola prosa/TOC generalizza fuori da Delphi. Dávila: fuori dal progetto.
