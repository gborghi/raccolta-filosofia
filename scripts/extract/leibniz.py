# scripts/extract/leibniz.py
"""Adapter bespoke per Gottfried Wilhelm Leibniz. Fonte: 'Collected Works of
Gottfried Wilhelm Leibniz', Delphi Classics, epub (Ops/, file NNN.html).

PROVENIENZA: Delphi Classics (modello PD del progetto). Leibniz † 1716: gli
originali sono in FRANCESE e LATINO (mai tedesco), qui in traduzioni inglesi
d'epoca tutte PD, verificate leggendo le righe "Translated by X" dell'epub:
Frederic Henry Hedge (1867), George Redington Montgomery (1908, Discourse on
Metaphysics / Monadology), Elizabeth Sanderson Haldane, Robert Latta (1898),
George Martin Duncan ('Philosophical Works', 1890). Tutte pre-1929 -> PD.
pd_year=1900.

SCELTA EDITORIALE — solo il testo d'AUTORE (INCLUDE_PREFIXES). Restano fuori
tutto l'apparato Delphi che nell'indice comincia da 'The Criticism' in poi:
i saggi SU Leibniz (Hegel 1837, Hedge 1858, Peirce 1899, Ward 1911), le
biografie e il catalogo Delphi. Struttura identica a hobbes.py/spinoza.py
(stesso editore, stessa forma epub): ogni opera e' [navPoint i, navPoint i+1)
nello spine; la SINOSSI editoriale Delphi in testa a ogni opera si scarta
partendo a raccogliere dalla prima testata strutturale (spinoza._CONTENT_HEAD).
"""
from __future__ import annotations

import glob
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .common import Work
from .sources import RAW_ROOT, Source
# Helper Delphi condivisi con Spinoza/Hobbes (stesso editore, stessa forma).
from .spinoza import (
    _CONTENT_HEAD,
    _SKIP_TITLE,
    _first_heading,
    _join,
    _opf_dir_and_spine,
    _paras_of,
    _read_ncx_toplevel,
    _title_of,
)

# Le 8 opere d'autore, per PREFISSO del titolo del navPoint (i titoli Delphi
# hanno anni fra parentesi e apostrofi/virgolette tipografiche: il prefisso e'
# robusto).
INCLUDE_PREFIXES = (
    "System of Theology",
    "Discourse on Metaphysics",
    "A Philosopher",                       # A Philosopher's Creed (1673)
    "Extracts from the",                   # …"New Essays on the Understanding" (1704)
    "Theodicy",
    "Monadology",
    "The Philosophical Works of Leibnitz",  # collezione Duncan 1890
    "Correspondence with Baruch Spinoza",
)
EXPECTED_WORKS = len(INCLUDE_PREFIXES)

# Confine di coda: da 'The Criticism' in poi e' tutto apparato (saggi su
# Leibniz, biografie, catalogo).
_APPARATUS_FROM = "the criticism"


@dataclass
class ExtractResult:
    works: list[Work]
    toc_titles: list[str]


def find_epub(source: Source) -> Path:
    cands = sorted(glob.glob(os.path.join(RAW_ROOT, source.key, "*.epub")))
    if not cands:
        raise FileNotFoundError(
            f"epub Leibniz (Delphi) non trovato in {os.path.join(RAW_ROOT, source.key)}"
        )
    return Path(cands[0])


def _included(title: str) -> bool:
    return any(title.startswith(p) for p in INCLUDE_PREFIXES)


def extract(epub_path: Path) -> ExtractResult:
    with zipfile.ZipFile(epub_path) as zf:
        opf_dir, spine = _opf_dir_and_spine(zf)
        pos = {href: k for k, href in enumerate(spine)}
        navs = _read_ncx_toplevel(zf)

        # confine di coda (primo navPoint d'apparato)
        app_idx = len(spine)
        for n in navs:
            if n.title.lower().startswith(_APPARATUS_FROM) and n.href in pos:
                app_idx = pos[n.href]
                break

        # tutti i navPoint noti prima dell'apparato: servono TUTTI per i confini
        # (anche i non inclusi delimitano i vicini).
        seq = [(n.title, pos[n.href]) for n in navs
               if n.href in pos and pos[n.href] < app_idx]
        seq.sort(key=lambda x: x[1])
        starts = [s for _, s in seq] + [app_idx]

        works: list[Work] = []
        for i, (title, lo) in enumerate(seq):
            if not _included(title):
                continue
            hi = starts[i + 1]

            def content_start(a: int, b: int) -> int:
                for k in range(a, b):
                    html = zf.read(_join(opf_dir, spine[k])).decode("utf-8", "replace")
                    if _CONTENT_HEAD.match(_first_heading(html)):
                        return k
                return a

            paras: list[str] = []
            for k in range(content_start(lo, hi), hi):
                html = zf.read(_join(opf_dir, spine[k])).decode("utf-8", "replace")
                t, h = _title_of(html), _first_heading(html)
                if _SKIP_TITLE.match(t) or _SKIP_TITLE.match(h):
                    continue
                paras.extend(_paras_of(zf, opf_dir, spine[k]))
            text = "\n\n".join(paras)
            if not text.strip():
                raise ValueError(f"opera Leibniz vuota: {title!r}")
            works.append(Work(title=title, text=text, kind="work"))

    if len(works) != EXPECTED_WORKS:
        raise ValueError(
            f"attese {EXPECTED_WORKS} opere, estratte {len(works)}: "
            f"{[w.title for w in works]}"
        )
    return ExtractResult(works=works, toc_titles=[w.title for w in works])
