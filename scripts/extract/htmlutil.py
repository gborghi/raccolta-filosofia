# scripts/extract/htmlutil.py
"""HTML -> testo nudo, condiviso da capital_en.py, kant_de.py e marx_de.py.

Estende il parser body-only di nietzsche.py (stessa idea: leggere solo <body>,
un newline per tag di blocco) con un meccanismo di skip per classe CSS. Serve
perche', a differenza dell'epub Nietzsche (dove il file-frontespizio si scarta
per intero), qui i marker di apparato vivono DENTRO lo stesso file del corpo:

- Kant (e-artnow): ogni file di capitolo ripete <div class="sgc"> con il link
  "Inhaltsverzeichnis" e un <h1 class="chapter5"> col titolo dell'opera, che
  duplicherebbe l'heading gia' scritto da common.render.
- Marx (andhof): stesso link di navigazione dentro <div class="sgc"> nei file
  del Kapital/Judenfrage/Hegel PoR.

skip_classes elenca le classi CSS il cui intero sottoalbero (tag e testo) va
scartato. Non e' usato per gli elementi self-closing (<br/>, <img/>): nei
corpus verificati non portano mai queste classi, quindi lo skip si applica
solo a tag aperti/chiusi con handle_starttag/handle_endtag ordinari.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

_BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "br", "li"}


class BodyTextExtractor(HTMLParser):
    def __init__(self, skip_classes: frozenset[str] = frozenset()) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._in_body = False
        self._skip_classes = skip_classes
        self._skip_depth = 0
        self._open_skip: list[bool] = []  # per ogni tag aperto: ha attivato skip?

    def _activates_skip(self, attrs) -> bool:
        cls = dict(attrs).get("class", "") or ""
        return bool(set(cls.split()) & self._skip_classes)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "body":
            self._in_body = True
            return
        if not self._in_body:
            return
        activates = self._activates_skip(attrs)
        self._open_skip.append(activates)
        if activates:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        # Self-closing (<br/>, <img/>): nessuno dei corpus verificati porta
        # skip_classes su questi tag, quindi non tocchiamo lo stack di skip.
        if self._in_body and not self._skip_depth and tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "body":
            self._in_body = False
            return
        if not self._open_skip:
            return
        if self._open_skip.pop():
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_body and not self._skip_depth:
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"[ \t]*\n[ \t]*", "\n", raw)
        raw = re.sub(r"\n{2,}", "\n\n", raw)
        return raw.strip()


def html_to_text(html: str, skip_classes: frozenset[str] = frozenset()) -> str:
    parser = BodyTextExtractor(skip_classes=skip_classes)
    parser.feed(html)
    return parser.text()
