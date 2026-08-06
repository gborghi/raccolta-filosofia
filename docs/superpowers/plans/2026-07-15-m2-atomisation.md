# M2 — Atomizzazione Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** spezzare le 115 opere (9M parole) in ~9.500 atomi di ~1.200 parole mediane.

**Architecture:** cascata con garanzia di taglia. (1) Le intestazioni si raccolgono da due fonti: le voci del `CONTENTS` dell'opera localizzate nel corpo, più i marker strutturali (`CHAPTER`, `BOOK`, `LETTER`, `SECTION`, numerazione romana/araba). (2) Ogni blocco fra intestazioni si spezza a confini di paragrafo fino al target. I confini semantici si usano dove ci sono; la taglia è garantita comunque.

**Tech Stack:** Python 3.12, pytest, stdlib.

## Global Constraints

- **Python:** solo `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe`.
- **Non toccare** `find_body_line`, `is_toc_occurrence`, `body_search_start`, `next_nonblank` in `scripts/extract/delphi_body.py`: validati su dati reali (116/116). Si **importano**.
- Input: `VaultPhilosophy/Philosophers/<Nome>/_raw/<OPERA>.md`. Output: `.../Atomized/<OPERA>/<NNN>_<slug>.md`.
- `VaultPhilosophy/` è gitignored.
- Commit: `git -c user.name="Giovanni Borghi" -c user.email="gio.borghi@gmail.com" commit -m "..."`
- Mai Gemini né backend non-Claude.

## Design validato sul corpus vero

Prototipato prima della stesura — due design precedenti sono stati **falsificati** così:

| tentativo | esito |
|---|---|
| Solo `CONTENTS`, con `pos` dall'ultima voce trovata in `lines[:400]` | 1.305 atomi, **95/115 opere non spezzate**. Bug: pescava l'occorrenza *nel corpo* invece della fine dell'indice |
| Solo `CONTENTS`, indice come blocco contiguo | 1.769 atomi, 57/115 non spezzate, **atomo massimo 136k parole** |
| **Cascata: intestazioni (CONTENTS + marker) + chunk per paragrafo** | **9.500 atomi, mediana 1.200, p99 1.499, 5 atomi >2.600** ✅ |

La lezione: il `CONTENTS` da solo non basta — non tutte le sue voci compaiono come header, e un'opera senza header resta un blocco inutilizzabile. La taglia va garantita, non sperata.

### Costanti (misurate)

```python
TARGET, MAX_WORDS, MIN_WORDS = 1500, 2600, 250
```

---

### Task 1: `contents_block` — l'indice come blocco contiguo

**Files:** Create `scripts/atomize/__init__.py`, `scripts/atomize/headings.py`; Test `tests/atomize/test_headings.py`

**Produces:** `contents_block(lines: list[str]) -> tuple[list[str], int]` → `(voci, indice_ultima_riga_indice)`

L'indice comincia a una riga `CONTENTS` fra le prime 40 righe e finisce alla prima riga di prosa (≥200 caratteri) o dopo 500 voci. **Deve restituire dove finisce**: il chiamante parte da lì. Il bug che ha ucciso il primo design era proprio cercare "l'ultima riga che assomiglia a una voce" — pescava le occorrenze nel corpo.

- [ ] **Step 1: test**

```python
# tests/atomize/test_headings.py
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
```

- [ ] **Step 2:** run → FAIL
- [ ] **Step 3: implementazione**

```python
# scripts/atomize/headings.py
"""Le intestazioni di un'opera, da due fonti.

Il CONTENTS sopravvive al taglio del blurb perche' appartiene all'edizione
originale (PD) e M1a lo classifica come materiale d'autore.
"""
from __future__ import annotations

import re

from scripts.extract.delphi_body import find_body_line

PROSE_MIN_LEN = 200
MAX_ENTRIES = 500
HEAD_WINDOW = 40
MAX_HEADING_LEN = 90

MARKERS = re.compile(
    r"^(CHAPTER|BOOK|LETTER|SECT(ION)?\.?|PART|EPISTLE)\s+[IVXLCDM0-9]", re.I)
ROMAN = re.compile(r"^[IVXLCDM]{1,7}\.(\s|$)")
NUMBERED = re.compile(r"^\d{1,3}\.(\s|$)")


def contents_block(lines: list[str]) -> tuple[list[str], int]:
    """(voci, riga in cui l'indice finisce). L'indice e' CONTIGUO."""
    ci = next((i for i, l in enumerate(lines[:HEAD_WINDOW])
               if l.strip() == "CONTENTS"), None)
    if ci is None:
        return [], 0
    entries: list[str] = []
    end = ci
    for i in range(ci + 1, len(lines)):
        s = lines[i].strip()
        if not s:
            continue
        if len(s) >= PROSE_MIN_LEN or len(entries) >= MAX_ENTRIES:
            break
        entries.append(s)
        end = i
    return entries, end
```

- [ ] **Step 4:** run → PASS (3)
- [ ] **Step 5:** commit

---

### Task 2: `heading_lines` — le due fonti unite

**Files:** Modify `scripts/atomize/headings.py`, `tests/atomize/test_headings.py`

**Produces:** `heading_lines(lines) -> tuple[dict[int, str], int]` → `({riga: titolo}, fine_indice)`

Le voci del `CONTENTS` si localizzano con `find_body_line` in **ricerca ordinata** (`pos` avanza) — senza, una voce si aggancia alla prima ricorrenza, che può essere una citazione. È lo stesso filtro che in M1a impediva ad `AGAMEMNON` di agganciarsi dentro `THE TROJAN WOMEN`.

Poi si aggiungono i marker strutturali con `setdefault` — il `CONTENTS` ha precedenza dove entrambi vedono la stessa riga.

- [ ] **Step 1: test**

```python
# append a tests/atomize/test_headings.py
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
```

- [ ] **Step 2:** run → FAIL
- [ ] **Step 3: implementazione**

```python
# append a scripts/atomize/headings.py

def heading_lines(lines: list[str]) -> tuple[dict[int, str], int]:
    """Righe che sono intestazioni: dal CONTENTS + dai marker strutturali."""
    entries, end = contents_block(lines)
    heads: dict[int, str] = {}

    # ricerca ORDINATA: pos avanza. Senza, una voce si aggancia a una
    # citazione precedente invece che alla sua sezione.
    pos = end + 1
    for title in entries:
        i = find_body_line(lines, title, pos, entries)
        if i is None:
            continue
        heads[i] = title
        pos = i + 1

    for i in range(end + 1, len(lines)):
        s = lines[i].strip()
        if not s or len(s) > MAX_HEADING_LEN:
            continue
        if MARKERS.match(s) or ROMAN.match(s) or NUMBERED.match(s):
            heads.setdefault(i, s)   # il CONTENTS ha precedenza
    return heads, end
```

- [ ] **Step 4:** run → PASS (7)
- [ ] **Step 5:** commit

---

### Task 3: `split_work` — chunk con garanzia di taglia

**Files:** Create `scripts/atomize/split.py`; Test `tests/atomize/test_split.py`

**Produces:** `Atom(title, text, n)`; `split_work(body: str) -> list[Atom]`

Ogni blocco fra intestazioni si spezza a **confini di paragrafo** fino a `TARGET`. È il pezzo che garantisce la taglia: senza, un'opera senza intestazioni resta un atomo da 136k parole (misurato).

Il testo prima della prima intestazione non si perde: diventa `(apertura)`.

- [ ] **Step 1: test**

```python
# tests/atomize/test_split.py
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
```

- [ ] **Step 2:** run → FAIL
- [ ] **Step 3: implementazione**

```python
# scripts/atomize/split.py
from __future__ import annotations

from dataclasses import dataclass

from .headings import heading_lines

TARGET = 1500
MAX_WORDS = 2600
MIN_WORDS = 250


@dataclass
class Atom:
    title: str
    text: str
    n: int


def _paragraphs(lines: list[str]) -> list[str]:
    paras: list[str] = []
    cur: list[str] = []
    for l in lines:
        if l.strip():
            cur.append(l)
        elif cur:
            paras.append("\n".join(cur))
            cur = []
    if cur:
        paras.append("\n".join(cur))
    return paras


def _chunk(lines: list[str], title: str, out: list[tuple[str, str]]) -> None:
    """Spezza a confini di paragrafo. Un paragrafo non si taglia mai a meta'."""
    buf: list[str] = []
    n = 0
    for p in _paragraphs(lines):
        w = len(p.split())
        if n and n + w > TARGET:
            out.append((title, "\n\n".join(buf)))
            buf, n = [p], w
        else:
            buf.append(p)
            n += w
    if buf:
        out.append((title, "\n\n".join(buf)))


def split_work(body: str) -> list[Atom]:
    lines = body.split("\n")
    heads, end = heading_lines(lines)
    ks = sorted(heads)
    out: list[tuple[str, str]] = []

    if not ks:
        _chunk(lines[end + 1:], "(intero)", out)
    else:
        if ks[0] > end + 1:
            _chunk(lines[end + 1: ks[0]], "(apertura)", out)
        for j, i in enumerate(ks):
            stop = ks[j + 1] if j + 1 < len(ks) else len(lines)
            _chunk(lines[i + 1: stop], heads[i], out)

    return [Atom(title=t, text=x, n=k + 1)
            for k, (t, x) in enumerate((t, x) for t, x in out if x.strip())]
```

- [ ] **Step 4:** run → PASS (6)
- [ ] **Step 5:** commit

---

### Task 4: emissione e CLI

**Files:** Create `scripts/atomize/run.py`; Test `tests/atomize/test_run.py`

**Produces:** `WorkReport(philosopher, work, atoms)`; `atomize_work(path, out_root) -> WorkReport`; `main() -> int`

Scrive `Atomized/<OPERA>/<NNN>_<slug>.md`. Frontmatter: eredita quello dell'opera (`philosopher`, `lang`, `edizione`, `traduttore`, `pd_year`, `source_key`) e aggiunge `work`, `atom_n`, `atom_title`, `kind: atom`. Riusa `slugify` da `scripts.extract.common`.

- [ ] **Step 1-5:** TDD; test su `tmp_path`, **mai** sul vault vero.
- [ ] **Step 6: run vero** `python -m scripts.atomize.run`
- [ ] **Step 7: ispezione a campione — testa, CENTRO e coda** di 3 atomi di 3 filosofi diversi. In M1a i marker `grouptxt.sh` erano sfuggiti a 63 opere su 115 **perché ispezionavo solo testa e coda**.

## Definition of Done

- Suite verde.
- `python -m scripts.atomize.run` esce 0.
- **~9.500 atomi**, mediana ~1.200 parole, p99 ~1.500, meno dell'1% sopra 2.600 (numeri del prototipo).
- Ispezione testa/centro/coda pulita.
