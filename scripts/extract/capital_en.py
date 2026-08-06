# scripts/extract/capital_en.py
"""Sostituisce la traduzione Untermann (Ernest Untermann, m. 1956, protetta
fino al 2027) di CAPITAL Volume I con la traduzione Moore & Aveling del 1887 --
Samuel Moore (m. 1911) ed Eleanor Marx Aveling (m. 1898), a cura di Friedrich
Engels: entrambi i traduttori morti da oltre 71 anni, PD.

Fonte: epub "Capital Volume I" pubblicato da Marxists Internet Archive
(https://www.marxists.org/archive/marx/works/download/epub/capital-v1.epub),
scaricato una tantum in RAW_ROOT/capital_en/Capital-Volume-I.epub. Il colophon
interno del file (Capital_Volume_I_split_000.htm) conferma testualmente:
"Translated: Samuel Moore and Edward Aveling, edited by Frederick Engels" --
non assunto, letto nel testo.

Struttura: un epub Calibre con un file per sezione (Capital_Volume_I_split_NNN.htm),
niente toc.ncx nidificato utile (i navPoint puntano 1:1 ai file split): i confini
si asseriscono per NUMERO DI FILE, verificati a mano leggendo head/tail di ognuno
(vedi la conversazione che ha prodotto questo modulo, non ripetuta qui):

- split_000: pagina colophon/traduttore -> apparato, esclusa.
- split_001: Table of Contents -> apparato, esclusa.
- split_002..008: le 7 Prefazioni/Postfazioni (Marx 1867/1872/1883, Engels
  1873/1875/1886/1890) -> corpo, incluse.
- split_009..051: le 8 Part e i 33 Chapter -> corpo, incluse.
- split_052..057: note a piè di libro raccolte in fondo (centinaia di endnote
  numerate) -> apparato editoriale/di trascrizione, escluse (stessa categoria
  di "note del curatore" che il committente chiede di non pubblicare). I
  numeri di richiamo restano nel corpo come cifre nude (l'hyperlink viene
  scartato dallo stripping HTML, il testo dello <span> resta).

Non e' un adapter generico riusabile: il range di file e' un'asserzione
esplicita (fail-closed nello spirito di aristotle.py/aquinas.py), non dedotta
da un TOC affidabile."""
from __future__ import annotations

import glob
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .common import Work
from .htmlutil import html_to_text
from .sources import RAW_ROOT

_FIRST_BODY_FILE = 2
_LAST_BODY_FILE = 51


@dataclass
class ExtractResult:
    works: list[Work] = field(default_factory=list)


def find_epub(raw_root: str = RAW_ROOT) -> Path:
    pattern = str(Path(raw_root) / "capital_en" / "*.epub")
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"nessun epub per capital_en: {pattern}")
    if len(paths) > 1:
        raise FileNotFoundError(f"piu' di un epub per capital_en: {paths}")
    return Path(paths[0])


def extract(epub_path: Path) -> ExtractResult:
    with zipfile.ZipFile(epub_path) as zf:
        parts = []
        for n in range(_FIRST_BODY_FILE, _LAST_BODY_FILE + 1):
            name = f"Capital_Volume_I_split_{n:03d}.htm"
            html = zf.read(name).decode("utf-8")
            chunk = html_to_text(html)
            if chunk:
                parts.append(chunk)
        text = "\n\n".join(parts)
    work = Work(
        title="CAPITAL",
        text=text,
        kind="work",
        traduttore="Samuel Moore and Edward Aveling",
    )
    return ExtractResult(works=[work])
