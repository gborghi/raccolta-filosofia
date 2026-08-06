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
