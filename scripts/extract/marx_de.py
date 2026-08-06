# scripts/extract/marx_de.py
"""Adapter bespoke per le opere Marx senza traduzione inglese PD: pubblica
l'originale tedesco (Marx m. 1883, nessun traduttore di mezzo -> PD di suo),
stesso principio di kant_de.py/nietzsche.py.

Fonte: RAW_ROOT/marx/Gesammelte Werke - Gesamtausgabe...epub (andhof, 2015,
lang=de). toc.ncx a due livelli come in kant_de.py (opere a depth 0, capitoli
a depth 1 come figli), file di corpo OEBPS/Text/index_split_NNN.html.

Le 3 opere della commessa (Zur Kritik der Hegelschen Rechtsphilosophie, Zur
Judenfrage, Zur Kritik der politischen Ökonomie) SOSTITUISCONO i _raw inglese
protetti gia' elencati nella commessa. Das Kapital II e III sono un'estensione
decisa qui, non nell'elenco originale della commessa (7 opere): il _raw
CAPITAL.md di Delphi risultava, aprendolo, contenere le TRE parti di Capital
concatenate sotto un solo titolo, tutte attribuite a Ernest Untermann (m.
1956, protetto). Il Volume I ha un'alternativa inglese PD (Moore & Aveling,
1887: vedi capital_en.py); i Volumi II e III no -- furono tradotti in inglese
SOLO da Untermann (1907-09), nessuna alternativa PD nota. Per la stessa
regola del committente ("inglese PD dove esiste, originale tedesco SOLO dove
non esiste") vanno quindi anch'essi convertiti al tedesco, altrimenti
resterebbe pubblicato materiale protetto sotto al titolo CAPITAL. Segnalato
come punto di decisione nel report finale, non eseguito silenziosamente.

Confini (verificati a mano leggendo head/tail di ogni file, non dedotti dal
TOC): tutti i file NON hanno mai il div.sgc di Kant (l'andhof non ripete un
mini-menu di navigazione per file), ma spesso duplicano il titolo dell'opera
in un h1/h2 subito dopo l'inizio -- gestito con _strip_leading_title(), non
con uno skip di classe CSS (le classi "block_NN" qui sono riusate senza
criterio semantico stabile, uno skip per classe rischierebbe di mangiare
paragrafi veri).

- HEGEL_POR: depth-0 "Zur Kritik der Hegelschen Rechtsphilosophie" (senza
  ancora) = index_split_228.html per intero fino a 248 incluso (il prossimo
  depth-0, "Lohn, Preis und Profit", comincia a 249). 228 apre con una decina
  di <h3> vuoti (frammenti di ancora orfani, nessun testo) poi il titolo
  duplicato h1+h2, poi "Einleitung" e il corpo vero ("Für Deutschland ist die
  Kritik der Religion...", incipit noto).
- JUDENFRAGE: depth-0 "Zur Judenfrage" (senza ancora) = index_split_294.html
  fino a 296 incluso (il prossimo, "Ökonomisch-philosophische Manuskripte...",
  comincia a 297). 294 apre con un h1 (titolo, non duplicato) poi una riga di
  data e un elenco puntato dei due testi di Bruno Bauer discussi (bibliografia
  minima, tenuta: e' la stessa nota che l'edizione inglese Delphi riportava,
  vedi data/work_starts.json["marx"]). Il file 296 finisce con l'explicit noto
  ("Die gesellschaftliche Emanzipation des Juden ist die Emanzipation der
  Gesellschaft vom Judentum.").
- KRITIK_POL_OEK: il depth-0 "Zur Kritik der politischen Ökonomie" (minuscolo,
  kids=3) raggruppa nell'ordine: [1] l'Introduzione ai Grundrisse ("I.
  Produktion, Konsumtion..."), [2] l'opera vera con ancora
  index_split_388.html#toc_id_203, [3] l'appendice dei Grundrisse "Formen, die
  der kapitalistischen Produktion vorhergehen" -- questi ultimi due NON sono
  Zur Kritik der politischen Ökonomie 1859, sono manoscritti dei Grundrisse
  raggruppati sotto lo stesso titolo in questa antologia (verificato leggendo
  l'incipit di ciascuno: "||15| Wenn wir so gesehn..." e "I. Produktion,
  Konsumtion, Distribution, Austausch" sono entrambi incipit noti dei
  Grundrisse, non del libro del 1859). Si usa quindi SOLO [2]: dentro
  index_split_388.html, dal byte dell'ancora toc_id_203 (dove ricomincia,
  identico, l'incipit noto del Vorwort 1859: "Ich betrachte das System der
  bürgerlichen Ökonomie...") fino a index_split_404.html incluso (405 apre
  "Formen..." = [3], escluso). C'e' anche un secondo depth-0 duplicato "Zur
  Kritik der Politischen Ökonomie" (maiuscola) a index_split_255.html: un solo
  file, contiene lo stesso Vorwort da solo, senza i capitoli. Scartato: il
  testo di 388-404 lo contiene per intero (Vorwort + Capitolo 1 "Die Ware" +
  Capitolo 2 "Das Geld" + note), quindi e' ridondante, non un'opera diversa.
- DAS_KAPITAL_II: depth-0 "Das Kapital II" (senza ancora) = index_split_081
  fino a 129 incluso (130 e' quasi tutto Fußnoten del Volume II, con
  l'intestazione "Das Kapital III" solo nelle ultime righe e nessun corpo
  dopo -- scartato per intero, vedi DAS_KAPITAL_III sotto).
- DAS_KAPITAL_III: il depth-0 "Das Kapital III" ha ancora #toc_id_56 dentro
  index_split_130.html, ma a quell'ancora il file finisce subito dopo
  l'intestazione (nessun corpo). Il corpo vero comincia in index_split_131
  ("Kritik der politischen Ökonomie / Dritter Band... Vorwort / Endlich ist
  es mir vergönnt...", incipit noto della prefazione di Engels) fino a 221
  incluso (222 e' un'opera diversa, la dissertazione di dottorato)."""
from __future__ import annotations

import glob
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZipFile

from .common import Work
from .htmlutil import html_to_text
from .sources import RAW_ROOT


@dataclass(frozen=True)
class WorkSpec:
    title: str
    first: int
    last: int
    start_anchor: str | None = None  # id HTML da cui tagliare dentro il primo file


_WORK_SPECS: list[WorkSpec] = [
    WorkSpec("Zur Kritik der Hegelschen Rechtsphilosophie", 228, 248),
    WorkSpec("Zur Judenfrage", 294, 296),
    WorkSpec("Zur Kritik der politischen Ökonomie", 388, 404, start_anchor="toc_id_203"),
    WorkSpec("Das Kapital II", 81, 129),
    WorkSpec("Das Kapital III", 131, 221),
]


@dataclass
class ExtractResult:
    works: list[Work] = field(default_factory=list)


def find_epub(raw_root: str = RAW_ROOT) -> Path:
    pattern = str(Path(raw_root) / "marx" / "*.epub")
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"nessun epub per marx_de: {pattern}")
    if len(paths) > 1:
        raise FileNotFoundError(f"piu' di un epub per marx_de: {paths}")
    return Path(paths[0])


def _cut_to_anchor(html: str, anchor: str) -> str:
    idx = html.find(f'id="{anchor}"')
    if idx == -1:
        raise ValueError(f"ancora {anchor!r} non trovata")
    tag_start = html.rfind("<", 0, idx)
    if tag_start == -1:
        raise ValueError(f"tag di apertura per l'ancora {anchor!r} non trovato")
    return html[tag_start:]


def _strip_leading_title(text: str, title: str) -> str:
    """Le pagine andhof spesso ripetono il titolo (h1 e/o h2) subito dopo
    l'inizio del corpo: common.render scrive gia' il suo H1, quindi le righe
    iniziali identiche al titolo (case-insensitive: 'Politischen' vs
    'politischen' nel TOC) sono ridondanti e vengono tolte. Righe successive
    (sottotitoli, curatore) non toccate."""
    lines = text.split("\n")
    target = title.strip().casefold()
    while lines and lines[0].strip().casefold() == target:
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines)


def _read_span(zf: ZipFile, spec: WorkSpec) -> str:
    parts = []
    for n in range(spec.first, spec.last + 1):
        html = zf.read(f"OEBPS/Text/index_split_{n:03d}.html").decode("utf-8")
        if n == spec.first and spec.start_anchor:
            html = _cut_to_anchor(html, spec.start_anchor)
        chunk = html_to_text(html)
        if chunk:
            parts.append(chunk)
    text = "\n\n".join(parts)
    return _strip_leading_title(text, spec.title)


def extract(epub_path: Path) -> ExtractResult:
    works: list[Work] = []
    with ZipFile(epub_path) as zf:
        for spec in _WORK_SPECS:
            text = _read_span(zf, spec)
            if not text:
                raise ValueError(f"corpo vuoto per {spec.title!r}")
            works.append(Work(title=spec.title, text=text, kind="work", traduttore=None))
    return ExtractResult(works=works)
