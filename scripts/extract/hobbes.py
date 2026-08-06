# scripts/extract/hobbes.py
"""Adapter bespoke per Thomas Hobbes. Fonte: 'Delphi Collected Works of Thomas
Hobbes', Delphi Classics, epub (Ops/, file NNN.html sequenziali).

PROVENIENZA: Delphi Classics (modello PD del progetto). Hobbes † 1679: le opere
originali inglesi (Leviathan ecc.) sono di pubblico dominio di per se'; le opere
latine (De Cive, De Corpore) qui compaiono nella traduzione inglese d'epoca, PD.
pd_year=1900. NB: le uniche sezioni latine dell'epub sono i due CARMI
(De Mirabilis Pecci, Historia Ecclesiastica), che NON pubblichiamo — quindi per
il corpus filosofico non c'e' latino a fronte (a differenza di Spinoza).

SCELTA EDITORIALE — solo il NUCLEO FILOSOFICO (INCLUDE_PREFIXES). Restano fuori,
per decisione dell'utente:
  - le TRADUZIONI che Hobbes fece di ALTRI autori (Tucidide, Iliade, Odissea,
    la Retorica di Aristotele): opera di Hobbes ma non il suo pensiero;
  - la POESIA e l'AUTOBIOGRAFIA;
  - le polemiche puramente MATEMATICHE (Six Lessons, Three Papers vs Wallis);
  - l'apparato Delphi (biografie, catalogo).
Il confine di coda e' 'The Translations': da li' in poi si scarta tutto.

STRUTTURA: come l'adapter Spinoza (Delphi). Ogni opera e' [navPoint i, navPoint
i+1) nello spine; la SINOSSI editoriale Delphi in testa a ogni opera si scarta
partendo a raccogliere dalla prima testata strutturale (spinoza._CONTENT_HEAD).
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from pathlib import Path

from .common import Work
from .sources import RAW_ROOT, Source
# Helper Delphi condivisi con l'adapter Spinoza (stesso editore, stessa forma).
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

HOBBES_EPUB_DIR = os.environ.get(
    "HOBBES_EPUB_DIR",
    "/Users/g.borghi/Library/CloudStorage/Dropbox/remotedir/libri/"
    "libri_svago/Saggi/filosofia/hobbes",
)

# Le 11 opere del nucleo filosofico, per PREFISSO del titolo del navPoint (i
# titoli Delphi sono lunghi e con apostrofi tipografici; il prefisso e' robusto,
# e "An Historical Narration concerning" evita il refuso "Hersey" dell'epub).
INCLUDE_PREFIXES = (
    "Elements of Law",
    "Of Liberty and Necessity",
    "De Cive",
    "Leviathan",
    "De Corpore",
    "Seven Philosophical Problems",
    "A Dialogue between a Philosopher",
    "An Answer to a Book Published by Dr. Bramhall",
    "Ten Dialogues of Natural Philosophy",
    "An Historical Narration concerning",
    "Behemoth",
)
EXPECTED_WORKS = len(INCLUDE_PREFIXES)

# Confine di coda: da 'The Translations' in poi e' tutto fuori nucleo/apparato.
_APPARATUS_FROM = "the translations"


@dataclass
class ExtractResult:
    works: list[Work]
    toc_titles: list[str] = field(default_factory=list)


def find_epub(source: Source) -> Path:
    for d in (HOBBES_EPUB_DIR, os.path.join(RAW_ROOT, "hobbes"), RAW_ROOT):
        cands = sorted(glob.glob(os.path.join(d, "*.epub")))
        hob = [c for c in cands if "hobbes" in os.path.basename(c).lower()]
        if hob:
            return Path(hob[0])
    raise FileNotFoundError(f"epub Hobbes (Delphi) non trovato in {HOBBES_EPUB_DIR}")


def _included(title: str) -> bool:
    return any(title.startswith(p) for p in INCLUDE_PREFIXES)


def extract(epub_path: Path) -> ExtractResult:
    import zipfile
    with zipfile.ZipFile(epub_path) as zf:
        opf_dir, spine = _opf_dir_and_spine(zf)
        pos = {href: k for k, href in enumerate(spine)}
        navs = _read_ncx_toplevel(zf)

        # confine di coda
        app_idx = len(spine)
        for n in navs:
            if n.title.lower().startswith(_APPARATUS_FROM) and n.href in pos:
                app_idx = pos[n.href]
                break

        # tutti i navPoint con inizio noto e prima dell'apparato: servono TUTTI
        # per calcolare i confini (anche quelli esclusi delimitano i vicini).
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
                raise ValueError(f"opera Hobbes vuota: {title!r}")
            works.append(Work(title=title, text=text, kind="work"))

    if len(works) != EXPECTED_WORKS:
        raise ValueError(
            f"attese {EXPECTED_WORKS} opere, estratte {len(works)}: "
            f"{[w.title for w in works]}"
        )
    return ExtractResult(works=works, toc_titles=[w.title for w in works])
