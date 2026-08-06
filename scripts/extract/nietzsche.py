# scripts/extract/nietzsche.py
"""Adapter bespoke per Nietzsche. Fonte: un solo file .epub tedesco (Anaconda
Verlag, testo originale PD dal 1971 -> Nietzsche morto 1900, nessun
traduttore di mezzo). NON e' un blob .txt come i Delphi: si apre con
zipfile e si legge il TOC (toc.ncx) per sapere quali sono le 7 opere
pubblicabili e dove iniziano nello spine.

Verificato a mano sul TOC reale (non un'assunzione):
- toc.ncx ha esattamente 7 navPoint, tutti "work" (nessuna voce apparato
  dentro il TOC stesso, a differenza dei Delphi).
- Ogni navPoint punta a un file Text/partNNNN.html che contiene SOLO il
  titolo dell'opera (pagina di frontespizio interna, nessun sottotitolo):
  va scartato, altrimenti duplica l'heading gia' scritto da common.render.
- Tra la fine di un'opera e l'inizio della successiva nello spine non ci
  sono file estranei: il corpo dell'opera N e' l'intervallo
  [start_num(N)+1, start_num(N+1)-1] (o fino all'ultimo file per l'ultima
  opera). L'apparato editoriale (Textgrundlage, Inhalt, titlepage) vive
  tutto PRIMA del primo navPoint (part0000-part0003) e non viene mai letto.
"""
from __future__ import annotations

import glob
import re
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from .common import Work
from .sources import RAW_ROOT, Source

NCX_NS = "{http://www.daisy.org/z3986/2005/ncx/}"
_PART_HREF_RE = re.compile(r"^Text/part(\d{4})\.html$")
_PART_NAME_RE = re.compile(r"^OEBPS/Text/part(\d{4})\.html$")
_BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "br"}

# Calibre ha reso qualche carattere greco come immagine invece che come testo,
# dove il font dell'edizione non lo copriva. Scartare il tag lascerebbe la parola
# mutilata: nella Genealogia I,5 si leggerebbe "ἐσλος" e "ἀγαος" invece di
# ἐσθλός e ἀγαθός — proprio nel passo etimologico su Teognide su cui Nietzsche
# costruisce l'argomento. Ogni glifo qui e' stato letto dal contesto nell'epub,
# non indovinato dal nome del file.
_IMG_GLYPH = {
    "00007.jpeg": "θ",  # ἐσ[θ]λος / ἀγα[θ]ος, Zur Genealogie der Moral
}


def _glyph_for(src: str) -> str:
    """Il carattere che l'immagine rappresenta, o "" se e' vera grafica.

    Ignoto = stringa vuota: un'immagine non mappata e' quasi sempre la copertina
    o un fregio, e inventare un carattere sarebbe peggio che ometterlo.
    """
    return _IMG_GLYPH.get(src.rsplit("/", 1)[-1].lower(), "")


class _BodyTextExtractor(HTMLParser):
    """Estrae testo nudo dal <body>. converts_charrefs=True (default in
    Python 3): le entita' HTML (umlaut ecc.) arrivano gia' decodificate a
    handle_data, non serve un unescape separato."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._in_body = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "body":
            self._in_body = True
            return
        if not self._in_body:
            return
        if tag == "img":
            # Un <img> in mezzo alla prosa e' un carattere che il font non
            # copriva, non un'illustrazione: va restituito al testo.
            self._chunks.append(_glyph_for(dict(attrs).get("src") or ""))
            return
        if tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "body":
            self._in_body = False

    def handle_data(self, data: str) -> None:
        if self._in_body:
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"[ \t]*\n[ \t]*", "\n", raw)
        raw = re.sub(r"\n{2,}", "\n\n", raw)
        return raw.strip()


def _html_to_text(html: str) -> str:
    parser = _BodyTextExtractor()
    parser.feed(html)
    return parser.text()


@dataclass
class TocEntry:
    title: str
    start_num: int


def find_epub(source: Source) -> Path:
    pattern = str(Path(RAW_ROOT) / source.key / source.glob)
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"nessun epub per {source.key}: {pattern}")
    if len(paths) > 1:
        raise FileNotFoundError(
            f"piu' di un epub per {source.key}, adapter si aspetta uno solo: {paths}"
        )
    return Path(paths[0])


def _parse_toc(zf: zipfile.ZipFile) -> list[TocEntry]:
    ncx = ET.fromstring(zf.read("OEBPS/toc.ncx"))
    entries: list[TocEntry] = []
    for nav in ncx.iter(f"{NCX_NS}navPoint"):
        label = nav.find(f"{NCX_NS}navLabel/{NCX_NS}text")
        content = nav.find(f"{NCX_NS}content")
        if label is None or content is None:
            continue
        src = content.get("src", "")
        m = _PART_HREF_RE.match(src)
        if m is None:
            # Ogni voce del TOC verificata punta a Text/partNNNN.html. Se
            # cambia formato non e' piu' terreno verificato: fail-closed.
            raise ValueError(f"voce TOC con href inatteso, non verificato: {src!r}")
        entries.append(TocEntry(title=(label.text or "").strip(), start_num=int(m.group(1))))
    if not entries:
        raise ValueError("toc.ncx senza navPoint: TOC vuoto o formato cambiato")
    return entries


def _max_part_num(zf: zipfile.ZipFile) -> int:
    nums = [int(m.group(1)) for name in zf.namelist() if (m := _PART_NAME_RE.match(name))]
    if not nums:
        raise ValueError("nessun file Text/partNNNN.html nell'epub")
    return max(nums)


@dataclass
class ExtractResult:
    works: list[Work] = field(default_factory=list)
    toc_titles: list[str] = field(default_factory=list)


def extract(epub_path: Path) -> ExtractResult:
    with zipfile.ZipFile(epub_path) as zf:
        entries = _parse_toc(zf)
        last_num = _max_part_num(zf)
        works: list[Work] = []
        for i, entry in enumerate(entries):
            end_num = entries[i + 1].start_num - 1 if i + 1 < len(entries) else last_num
            # start_num stesso e' la pagina-frontespizio (solo titolo):
            # si scarta, il corpo comincia dal file successivo.
            body_parts = []
            for num in range(entry.start_num + 1, end_num + 1):
                html = zf.read(f"OEBPS/Text/part{num:04d}.html").decode("utf-8")
                chunk = _html_to_text(html)
                if chunk:
                    body_parts.append(chunk)
            works.append(Work(title=entry.title, text="\n\n".join(body_parts), kind="work"))
    return ExtractResult(works=works, toc_titles=[e.title for e in entries])
