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
    skipped: list[str] = field(default_factory=list)


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
            # "work" e "latin" vengono entrambi pubblicati: entrambi vanno
            # segnalati se mai localizzati. Solo "apparatus" non conta.
            if e.kind in ("work", "latin"):
                missing.append(e.title)
            continue
        located.append((idx, e))
        pos = idx + 1

    works: list[Work] = []
    unmarked: list[str] = []
    skipped: list[str] = []
    for n, (idx, entry) in enumerate(located):
        if entry.kind == "apparatus":
            continue
        end = located[n + 1][0] if n + 1 < len(located) else len(lines)
        body = "\n".join(lines[idx + 1: end])

        # Divisori di sezione Delphi (es. lucretius/The Latin Text, The Dual
        # Text): non sono opere, il loro intero corpo è una didascalia
        # d'immagine. Contati esplicitamente (non aritmeticamente da un
        # elenco esterno) cosi' una riga "skip" bogus per un titolo mai
        # localizzato non puo' mascherare un'opera davvero non pubblicata.
        info = starts.get(entry.title)
        if info is not None and info.get("skip"):
            skipped.append(entry.title)
            continue

        # data/work_starts.json dice dove finisce il blurb editoriale Delphi
        # e comincia il testo d'autore. Il confine di copyright deve essere
        # un'asserzione ESPLICITA: la chiave "first_line" deve essere
        # presente. Solo "first_line": "" scritta a mano significa
        # "verificato: nessun blurb". Assente (chiave o intera entry) =
        # non lo sappiamo: si segnala, non si pubblica a caso (fail-closed).
        if info is None or "first_line" not in info:
            unmarked.append(entry.title)
            continue
        clean, found = strip_to_start(body, info["first_line"])
        # Vuoto dopo il taglio e' un fallimento pari a "marker non trovato"
        # (verify_starts.py lo tratta cosi'): non si scarta in silenzio.
        if not found or not clean:
            unmarked.append(entry.title)
            continue
        works.append(Work(title=entry.title, text=clean, kind=entry.kind,
                          traduttore=info.get("traduttore")))

    return ExtractResult(works=works, missing=missing, unmarked=unmarked, skipped=skipped)
