# scripts/extract/marx_inaugural_en.py
"""MARXS_INAUGURAL_ADDRESS.md: Delphi accredita "Alick West" come traduttore
(m. 1972, protetto), ma l'Inaugural Address of the International Working
Men's Association (1864) non e' una traduzione -- Marx la scrisse
direttamente in inglese, lingua di lavoro della IWA fondata a Londra il 28
settembre 1864 al St. Martin's Hall. Confermato incrociando piu' fonti
(Marxists Internet Archive, Internet Archive, letteratura storica sulla
Prima Internazionale): nessuna menziona un traduttore, tutte la trattano
come originale inglese di Marx.

Riprova indipendente della necessita' di questo fix, trovata leggendo il
corpo esistente in Marx/_raw/MARXS_INAUGURAL_ADDRESS.md: sotto il credito
"Translated by Alick West" il testo estratto da Delphi non e' affatto
l'Inaugural Address, ma l'indice di Engels, "The Origin of the Family,
Private Property and the State" (Preface to the First Edition 1884, Stages
of Prehistoric Culture, Iroquois/Greek/Roman Gens...) -- un mismatch gia'
segnalato a mano in data/work_starts.json come "SUSPECT MISMATCH". Il
credito a West era quindi doppiamente sbagliato: traduttore inesistente per
un testo che non e' nemmeno quello giusto.

Fonte: https://www.marxists.org/archive/marx/works/1864/10/27.htm, scaricato
in RAW_ROOT/marx_inaugural_en/inaugural-address.htm. Confini nel file:
- <p class="fst"> compare due volte: la prima apre il corpo ("Workingmen:
  It is a great fact..."), la seconda apre l'unica nota a pie' di pagina
  firmata da Marx stesso ("-- K.M."), che e' quindi testo d'autore e resta.
- <p class="information"> (Written/First Published/Source/Transcription) e
  <p class="footer"> (link di navigazione del sito) sono apparato del sito,
  non del testo: esclusi tagliando rispettivamente prima del primo <p
  class="fst"> e da <p class="footer"> in poi.
"""
from __future__ import annotations

import glob
from dataclasses import dataclass, field
from pathlib import Path

from .common import Work
from .htmlutil import html_to_text
from .sources import RAW_ROOT

_START_MARKER = '<p class="fst">'
_END_MARKER = '<p class="footer">'


@dataclass
class ExtractResult:
    works: list[Work] = field(default_factory=list)


def find_html(raw_root: str = RAW_ROOT) -> Path:
    pattern = str(Path(raw_root) / "marx_inaugural_en" / "*.htm*")
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"nessun htm per marx_inaugural_en: {pattern}")
    if len(paths) > 1:
        raise FileNotFoundError(f"piu' di un htm per marx_inaugural_en: {paths}")
    return Path(paths[0])


def extract(html_path: Path) -> ExtractResult:
    html = html_path.read_text(encoding="utf-8", errors="replace")
    start = html.find(_START_MARKER)
    end = html.find(_END_MARKER, start)
    if start == -1 or end == -1:
        raise ValueError(
            f"marker di confine non trovati in {html_path}: "
            f"start={start} end={end} (pagina cambiata?)"
        )
    body_html = html[start:end]
    text = html_to_text(f"<body>{body_html}</body>")
    if not text:
        raise ValueError(f"corpo vuoto dopo il taglio in {html_path}")
    work = Work(
        title="MARX’S INAUGURAL ADDRESS",
        text=text,
        kind="work",
        traduttore=None,
    )
    return ExtractResult(works=[work])
