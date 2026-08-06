# scripts/extract/schopenhauer.py
"""Adapter bespoke per Schopenhauer. Fonte: un solo .epub tedesco ("Gesammelte
Werke", calibre, testo originale PD -> Schopenhauer morto 1860, nessun
traduttore di mezzo; l'"Alle Rechte vorbehalten" della ristampa e' boilerplate
su testo PD, come per Nietzsche/Anaconda). Stessa macchina epub di
nietzsche.py (layout OEBPS/Text/partNNNN.html), ma il TOC NON e' una lista
piatta di opere: e' annidato fino al singolo §, e i navPoint depth-0 mescolano
i Bücher di WWR, le Ergänzungen e i saggi. Percio' i confini d'opera NON si
leggono dal TOC ma sono un elenco esplicito, verificato a mano sul toc.ncx
reale (schema hobbes.INCLUDE_PREFIXES: elenco curato, non euristica sul TOC).

Copertura verificata (falsi positivi del grep esclusi leggendo gli heading):
questo epub NON e' l'opera omnia. Contiene Die Welt als Wille und Vorstellung
I + II (completo, con Kritik der Kantischen Philosophie) piu' una selezione:
Geistersehn, Über die Weiber, Eristische Dialektik, Aphorismen zur
Lebensweisheit, Nachlaß, Einleitung in die Philosophie, Abhandlungen. ASSENTI
come opere: vierfache Wurzel, Willen in der Natur, i due Grundprobleme der
Ethik, gran parte di Parerga (compaiono solo come menzioni dentro WWR). I buchi
sono un ingest successivo (Zeno.org, tedesco PD).

Ogni tupla e' (part_num del primo file dell'opera nello spine, titolo). Il
corpo dell'opera N e' l'intervallo [start(N), start(N+1)-1] (o fino all'ultimo
part per l'ultima). part0000-part0001 (frontespizio Sämtliche Werke + pagina
"I") stanno PRIMA del primo confine e non vengono mai letti. I sotto-heading
(Erster Band, Vorworte, Erstes Buch, §§) restano dentro il corpo dell'opera e
diventano i confini che l'atomizzatore usa per i leaf atom.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .common import Work
from .nietzsche import _html_to_text, _max_part_num, find_epub  # stessa macchina epub

# Confini d'opera (part_num, titolo). Titoli SENZA em-dash: slugify() tronca sul
# " — " (multi-tomo), quindi "WWR — Erster/Zweiter Band" collidirebbe sullo
# stesso slug; con il punto ("Erster Band.") gli slug restano distinti.
WORKS: list[tuple[int, str]] = [
    (2,  "Die Welt als Wille und Vorstellung. Erster Band"),
    (31, "Die Welt als Wille und Vorstellung. Zweiter Band"),
    (64, "Über das Geistersehn und was damit zusammenhängt"),
    (68, "Über die Weiber"),
    (69, "Die Kunst, Recht zu behalten"),
    (70, "Aphorismen zur Lebensweisheit"),
    (76, "Handschriftlicher Nachlaß"),
    (77, "Einleitung in die Philosophie"),
    (82, "Abhandlungen"),
]


@dataclass
class ExtractResult:
    works: list[Work] = field(default_factory=list)
    toc_titles: list[str] = field(default_factory=list)


# Sotto questa soglia un'opera e' un moncone d'apparato, non testo: part0076
# ("Handschriftlicher Nachlaß") e' una nota editoriale di ~300 char, il vero
# Nachlaß non e' in questo epub. Si tiene comunque il suo confine in WORKS
# (cosi' Aphorismen resta correttamente delimitata a [70,75]) ma non lo si
# pubblica come opera.
_MIN_WORK_CHARS = 500


def extract(epub_path: Path) -> ExtractResult:
    with zipfile.ZipFile(epub_path) as zf:
        last_num = _max_part_num(zf)
        works: list[Work] = []
        for i, (start, title) in enumerate(WORKS):
            end = WORKS[i + 1][0] - 1 if i + 1 < len(WORKS) else last_num
            body_parts: list[str] = []
            for num in range(start, end + 1):
                name = f"OEBPS/Text/part{num:04d}.html"
                try:
                    raw = zf.read(name).decode("utf-8")
                except KeyError:
                    # buco nella numerazione: fail-closed sarebbe eccessivo qui
                    # (lo spine puo' saltare numeri), si salta il file assente.
                    continue
                # L'epub usa CRLF: nietzsche._html_to_text normalizza solo \n,
                # i \r residui sporcherebbero gli heading che l'atomizzatore
                # legge. Si normalizzano i fine-riga prima del parsing.
                html = raw.replace("\r\n", "\n").replace("\r", "\n")
                chunk = _html_to_text(html)
                if chunk:
                    body_parts.append(chunk)
            text = "\n\n".join(body_parts)
            if len(text) < _MIN_WORK_CHARS:
                continue  # moncone d'apparato, non un'opera
            works.append(Work(title=title, text=text, kind="work"))
    return ExtractResult(works=works, toc_titles=[w.title for w in works])
