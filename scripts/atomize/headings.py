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

# Struttura scolastica (Summa Theologica di Tommaso d'Aquino, unica fonte
# oggi che la usa): Quaestio -> Articulus. Marcatori aggiunti QUI (non solo
# nell'adapter aquinas.py) perche' e' qui che un'intestazione diventa un
# confine di atomo per split.py - l'adapter si limita a ricostruire i
# paragrafi (righe vuote), non decide i tagli.
#
# QUAESTIO: riga che finisce con "(<numero in lettere> ARTICLE[S])", es.
# "OF THE ESSENCE OF LAW (FOUR ARTICLES)". Pattern verificato su tutto il
# corpus Aquinas (562 occorrenze, 0 falsi positivi, vedi aquinas.py) e per
# costruzione innocuo altrove: nessun'altra fonte del progetto (Delphi,
# Nietzsche, Ortega, Rousseau, Descartes, Plato, Aristotle) usa la dicitura
# "(<parola numerica> ARTICLE/S)" a fine riga - confermato confrontando i
# conteggi di atomizzazione prima/dopo per ognuna (vedi verifica).
# Lunghezza max osservata dopo il join delle intestazioni andate a capo: 164
# caratteri (QQ_ARTICULUS_MAX_LEN copre con margine, MAX_HEADING_LEN normale
# la escluderebbe).
#
# ARTICULUS: la domanda dell'articolo, "Whether ...?" - una riga che INIZIA
# per "Whether" e FINISCE con "?" (eventualmente seguita da una nota del
# traduttore fra parentesi quadre chiusa sulla stessa riga). Questo pattern
# e' meno esclusivo del precedente (una frase retorica "Whether X?" isolata
# come proprio paragrafo puo' capitare in altri filosofi, es. Platone), per
# questo qui si richiede ANCHE che la riga sia ISOLATA - riga vuota prima E
# dopo (o inizio/fine testo) - una condizione che l'adapter aquinas.py
# garantisce sempre per le vere domande d'articolo (sono marcatori, la riga
# vuota precede ogni marcatore per costruzione, e la riga dopo - sempre
# "Objection 1:" - e' anch'essa un marcatore) ma che la prosa ordinaria di
# un'opera con paragrafi normali raramente soddisfa per un'unica frase
# isolata. Verificato con lo stesso confronto conteggi prima/dopo.
QQ_ARTICULUS_MAX_LEN = 200
QUAESTIO = re.compile(
    r"\((?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|"
    r"THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|"
    r"TWENTY(?:-\w+)?|THIRTY(?:-\w+)?)\s+ARTICLES?\)\s*$"
)
ARTICULUS = re.compile(r"^Whether\b.{0,190}\?(?:\s*\[[^\]]*\])?\.?\s*[\"'”’]?\s*$")

# Struttura tedesca (Schopenhauer, unica fonte tedesca con struttura interna
# oltre a Nietzsche che invece e' aforistico): i §§ dei quattro Bücher di WWR,
# i Kapitel delle Ergänzungen/Parerga, i Bücher stessi, i 38 Kunstgriffe
# dell'Eristische Dialektik, i Theile dell'Einleitung. Additivo come i
# marcatori latini di Aquinas: le parole tedesche (Buch/Kapitel/Kunstgriff/
# Theil) e il simbolo § a inizio riga non compaiono in nessun'altra fonte del
# progetto (EN/LA/FR/ES/GRC), quindi non alterano l'atomizzazione altrove.
GERMAN = re.compile(
    r"^(?:"
    r"§+\.?\s*\d{1,3}"                                                   # §. 1.  / § 17
    r"|(?:Erstes|Zweites|Drittes|Viertes|Fünftes|Sechstes|Siebtes|Achtes|Neuntes)\s+Buch"
    r"|Kapitel\s+(?:\d{1,3}|[IVXLC]{1,6})\b"                             # Kapitel 12. Zur…
    r"|Kunstgriff\s+\d{1,2}"                                             # Kunstgriff 1..38
    r"|(?:Erster|Zweiter|Dritter|Vierter)\s+Theil"
    r"|Ergänzungen\s+zum"
    r")"
)


def _isolated(lines: list[str], i: int) -> bool:
    """True se la riga i e' un intero paragrafo per conto suo (riga vuota,
    o inizio/fine testo, sui due lati)."""
    before_ok = i == 0 or not lines[i - 1].strip()
    after_ok = i + 1 >= len(lines) or not lines[i + 1].strip()
    return before_ok and after_ok


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
        if len(s) >= PROSE_MIN_LEN or len(entries) >= MAX_ENTRIES or s in entries:
            break
        entries.append(s)
        end = i
    return entries, end


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

    # end=0 e' anche il default "nessun CONTENTS" (vedi contents_block):
    # in quel caso non e' la fine di un indice, e la riga 0 puo' essere
    # un'intestazione legittima che non va saltata.
    marker_start = end + 1 if entries else 0
    for i in range(marker_start, len(lines)):
        s = lines[i].strip()
        if not s:
            continue
        if len(s) <= MAX_HEADING_LEN and (
            MARKERS.match(s) or ROMAN.match(s) or NUMBERED.match(s) or GERMAN.match(s)
        ):
            heads.setdefault(i, s)   # il CONTENTS ha precedenza
            continue
        if len(s) > QQ_ARTICULUS_MAX_LEN:
            continue
        if QUAESTIO.search(s):
            heads.setdefault(i, s)
        elif ARTICULUS.match(s) and _isolated(lines, i):
            heads.setdefault(i, s)
    # contents_block pins end=0 anche per "nessun CONTENTS" (vedi il suo
    # stesso test). Per i chiamanti che usano end+1 come punto di taglio
    # (split_work) 0 va disambiguato: -1 quando non c'era un indice reale,
    # cosi' end+1 torna a significare "niente consumato, si parte da 0".
    return heads, (end if entries else -1)
