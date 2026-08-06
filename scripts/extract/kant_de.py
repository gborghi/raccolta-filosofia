# scripts/extract/kant_de.py
"""Adapter bespoke per le 2 opere Kant senza traduzione inglese PD (vedi
CLAUDE della commessa): l'originale tedesco e' PD di suo (Kant m. 1804,
nessun traduttore di mezzo), quindi si pubblica quello, come gia' fa
nietzsche.py per Nietzsche.

Fonte: RAW_ROOT/kant/[Sämtliche Werke 01]...epub (e-artnow, 2016, lang=de),
lo stesso file gia' usato come prova per la commessa. A differenza
dell'epub Nietzsche, il toc.ncx qui ha ~700 navPoint ANNIDATI: i figli
diretti della navMap (depth 0) sono le opere (o separatori di sezione senza
figli, es. "Philosophische Schriften"), i loro navPoint-figli (depth 1) sono
i capitoli interni. Confini verificati a mano (non dedotti automaticamente):

- ALLGEMEINE_NATURGESCHICHTE: depth-0 navPoint "Allgemeine Naturgeschichte
  und Theorie des Himmels" punta a text/part0011.html, che pero' contiene
  SOLO il frontespizio (h1 col titolo + mini-indice dei figli, nessun testo
  di Kant) -- stesso pattern del file-frontespizio di nietzsche.py: si
  scarta. Il corpo vero comincia a part0012.html (la dedica al re di
  Prussia) e finisce a part0026.html incluso (il depth-0 successivo,
  "Von den Ursachen der Erderschütterungen...", comincia a part0027.html).
- BEANTWORTUNG (Was ist Aufklärung): depth-0 navPoint senza figli, un solo
  file, text/part0307.html: contiene sia il frontespizio (h1 duplicato +
  div.sgc di navigazione) sia l'intero corpo nello stesso file, quindi non
  si puo' scartare il file intero -- si scartano solo l'h1 col titolo
  (classe "chapter5", ridondante con l'heading che scrive common.render) e
  il div.sgc di rimando all'Inhaltsverzeichnis, via htmlutil.html_to_text.

Non e' un walker generico del TOC (a differenza di nietzsche.py, che
pubblica tutti i 7 navPoint): qui servono solo 2 delle ~70 opere di primo
livello, selezionate a mano, quindi i confini sono un'asserzione esplicita
per titolo (fail-closed: KeyError se il titolo sparisce dal TOC)."""
from __future__ import annotations

import glob
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZipFile

from .common import Work
from .htmlutil import html_to_text
from .sources import RAW_ROOT

_SKIP_CLASSES = frozenset({"sgc", "chapter5"})

# title -> (primo file corpo incluso, ultimo file corpo incluso)
_WORK_SPANS: dict[str, tuple[int, int]] = {
    "Allgemeine Naturgeschichte und Theorie des Himmels": (12, 26),
    "Beantwortung der Frage: Was ist Aufklärung": (307, 307),
}


@dataclass
class ExtractResult:
    works: list[Work] = field(default_factory=list)


def find_epub(raw_root: str = RAW_ROOT) -> Path:
    pattern = str(Path(raw_root) / "kant" / "*.epub")
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"nessun epub per kant_de: {pattern}")
    if len(paths) > 1:
        raise FileNotFoundError(f"piu' di un epub per kant_de: {paths}")
    return Path(paths[0])


def _read_span(zf: ZipFile, first: int, last: int) -> str:
    parts = []
    for n in range(first, last + 1):
        html = zf.read(f"text/part{n:04d}.html").decode("utf-8")
        chunk = html_to_text(html, skip_classes=_SKIP_CLASSES)
        if chunk:
            parts.append(chunk)
    return "\n\n".join(parts)


def extract(epub_path: Path) -> ExtractResult:
    works: list[Work] = []
    with ZipFile(epub_path) as zf:
        for title, (first, last) in _WORK_SPANS.items():
            text = _read_span(zf, first, last)
            if not text:
                raise ValueError(f"corpo vuoto per {title!r} (part{first:04d}-part{last:04d})")
            works.append(Work(title=title, text=text, kind="work", traduttore=None))
    return ExtractResult(works=works)
