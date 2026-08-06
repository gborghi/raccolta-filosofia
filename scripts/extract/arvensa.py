# scripts/extract/arvensa.py
"""Motore condiviso per le fonti Arvensa Editions (epub). Bespoke per Cartesio
(epub, toc.ncx a 2 livelli). Se Rousseau (altra fonte Arvensa, oggi .txt)
dovesse passare a un epub con la stessa struttura, questo modulo e' pensato
per essere riusato cosi' com'e' -- non toccare rousseau.py da qui, coordinare
via report se serve condividere altro.

Verificato a mano sul TOC reale (non un'assunzione):
- OEBPS/toc.ncx ha 212 navPoint totali (211 dopo la radice + radice stessa
  a seconda di come si conta; conteggio ncx.iter('navPoint') = 212), non 213:
  qualunque numero atteso va riverificato contro il file reale, non fidarsi
  di un conteggio a occhio.
- Struttura a 2 livelli soltanto (max depth = 1): 31 voci top-level, ciascuna
  con 0+ figlie dirette (nessuna nipote).
- Le voci "opera" sono le 19 top-level in TUTTO MAIUSCOLO che non sono ne'
  apparato editoriale noto ne' intestazioni di sezione "-- X --" ne' voci
  d'apparato con attribuzione esplicita a un curatore "(par ...)" (le 3 voci
  ANNEXES: critica letteraria, elogio, biografia -- scritte da altri autori,
  non da Descartes).
- Ogni opera "reale" nello spine comincia con 3 file di apparato PRIMA della
  sua prima voce-figlia nel TOC: pagina di frontespizio (titolo + boilerplate
  pubblicitario Arvensa), un file-stub con solo un riferimento a nota a piè
  di pagina, e una nota bibliografica editoriale in terza persona (talvolta
  firma esplicitamente il curatore, es. "Edition numerique sous la direction
  de : Geoffroy Ambroy"). Questo blocco NON viene mai letto: il corpo
  dell'opera e' l'unione delle sole voci-figlie incluse (mai il file
  dell'intestazione top-level stessa).
- "Table des matieres" (indice locale dell'opera) e' apparato: sempre
  escluso, per ogni opera.
- Alcune voci-figlie sono apparato SOLO in certe opere (es. "Introduction" e'
  il sommario autentico di Descartes nel Discours, ma e' una nota editoriale
  del curatore ne Le Monde e nel Traite de l'Homme; "Avertissement" e' di
  Descartes nella Geometrie ma del curatore nelle Premieres Pensees) -- non
  classificabile per solo titolo, richiede una coppia (opera, titolo) esplicita
  verificata a mano leggendo il contenuto (vedi cartesio.py).
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
OPF_NS = "{http://www.idpf.org/2007/opf}"
_BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "br", "li"}

# Furniture di navigazione ripetuta su OGNI pagina (verificato: 1375 coppie
# nell'epub, non solo sulla prima pagina di ogni voce), non contenuto:
# <p class="NavigationCentreVert"> ripete il titolo dell'opera, <p
# class="NavigationHyperlinks"> contiene i link "Liste des titres" / "Table
# des matieres du titre". Senza filtrarle si inietterebbero 2-3 volte per
# pagina dentro il corpo estratto.
_NAV_CLASSES = {"NavigationCentreVert", "NavigationHyperlinks"}

# Richiami di nota del curatore, attaccati alla parola: "raide[380]",
# "éolipyles[384]", "ornithies[385]". Le note vere vivono negli annexes, che sono
# apparato e non vengono pubblicati — quindi questi numeri non rimandano a nulla:
# restano solo cifre in mezzo alla prosa di Descartes. 2015 occorrenze, di cui
# 1564 nelle sole LETTRES.
#
# Il limite a 4 cifre e l'assenza di spazi interni tengono fuori i casi in cui la
# parentesi quadra e' testo (un inciso, un rinvio dell'autore): un richiamo di
# nota e' sempre e solo un numero nudo.
_NOTE_REF = re.compile(r"\[\d{1,4}\]")


class _BodyTextExtractor(HTMLParser):
    """Estrae testo nudo dal <body>. converts_charrefs=True (default in
    Python 3): le entita' HTML arrivano gia' decodificate a handle_data."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._in_body = False
        self._suppress = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "body":
            self._in_body = True
            return
        if tag == "p":
            classes = dict(attrs).get("class", "") or ""
            if _NAV_CLASSES & set(classes.split()):
                self._suppress = True
        if self._in_body and tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "body":
            self._in_body = False
        if tag == "p":
            self._suppress = False

    def handle_data(self, data: str) -> None:
        if self._in_body and not self._suppress:
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        raw = _NOTE_REF.sub("", raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"[ \t]*\n[ \t]*", "\n", raw)
        raw = re.sub(r"\n{2,}", "\n\n", raw)
        return raw.strip()


def _html_to_text(html: str) -> str:
    parser = _BodyTextExtractor()
    parser.feed(html)
    return parser.text()


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


@dataclass
class NcxEntry:
    title: str
    href: str
    depth: int


def parse_spine_order(zf: zipfile.ZipFile) -> list[str]:
    """Ordine di lettura reale (content.opf/spine), non l'ordine alfabetico
    dei nomi file: alcuni Section*.htm sono intercalati fuori sequenza
    numerica rispetto ai File_*.htm."""
    opf = ET.fromstring(zf.read("OEBPS/content.opf"))
    manifest_el = opf.find(f"{OPF_NS}manifest")
    spine_el = opf.find(f"{OPF_NS}spine")
    if manifest_el is None or spine_el is None:
        raise ValueError("content.opf senza manifest o spine")
    manifest = {item.get("id"): item.get("href") for item in manifest_el.findall(f"{OPF_NS}item")}
    hrefs = [manifest[ir.get("idref")] for ir in spine_el.findall(f"{OPF_NS}itemref")]
    if not hrefs:
        raise ValueError("spine vuoto")
    return hrefs


def parse_toc_flat(zf: zipfile.ZipFile) -> list[NcxEntry]:
    """Appiattisce toc.ncx in preorder DFS, preservando la profondita'.
    L'ordine di visita coincide con l'ordine di lettura (verificato contro
    lo spine, non assunto)."""
    ncx = ET.fromstring(zf.read("OEBPS/toc.ncx"))
    navmap = ncx.find(f"{NCX_NS}navMap")
    if navmap is None:
        raise ValueError("toc.ncx senza navMap")
    flat: list[NcxEntry] = []

    def walk(nav, depth: int) -> None:
        label = nav.find(f"{NCX_NS}navLabel/{NCX_NS}text")
        content = nav.find(f"{NCX_NS}content")
        if label is None or content is None:
            return
        flat.append(NcxEntry(
            title=(label.text or "").strip(),
            href=content.get("src", ""),
            depth=depth,
        ))
        for child in nav.findall(f"{NCX_NS}navPoint"):
            walk(child, depth + 1)

    for nav in navmap.findall(f"{NCX_NS}navPoint"):
        walk(nav, 0)
    if not flat:
        raise ValueError("toc.ncx senza navPoint: TOC vuoto o formato cambiato")
    return flat


def is_section_divider(title: str) -> bool:
    """Intestazioni di sezione tipo '— ŒUVRES PHILOSOPHIQUES —':
    non sono opere ne' apparato con contenuto proprio, solo raggruppatori."""
    return len(title) > 1 and title.startswith("—") and title.endswith("—")


def is_other_author_apparatus(title: str) -> bool:
    """Voci esplicitamente attribuite a un autore diverso da Descartes,
    es. 'ELOGE DE RENE DESCARTES(par Antoine Leonard Thomas)'."""
    return "(par " in title


@dataclass
class ExtractResult:
    works: list[Work] = field(default_factory=list)
    found: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unexpected_top: list[str] = field(default_factory=list)


def extract(
    source: Source,
    expected_works: list[str],
    known_apparatus_titles: set[str],
    exclude_child_pairs: set[tuple[str, str]],
    universal_exclude_children: set[str] = frozenset({"Table des matières"}),
) -> ExtractResult:
    """Estrae le opere di `expected_works` (asserzione esplicita, come
    data/work_starts.json per Delphi: fail-closed, non un'euristica libera).
    Ogni voce top-level del TOC che non e' ne' un'opera attesa ne' apparato
    noto ne' intestazione di sezione ne' apparato-di-altro-autore finisce in
    `unexpected_top`, segnale che il TOC e' cambiato rispetto a quanto
    verificato a mano."""
    epub_path = find_epub(source)
    expected_set = set(expected_works)
    with zipfile.ZipFile(epub_path) as zf:
        spine = parse_spine_order(zf)
        spine_index = {h: i for i, h in enumerate(spine)}
        flat = parse_toc_flat(zf)

        top_positions = [i for i, e in enumerate(flat) if e.depth == 0]
        found: list[str] = []
        unexpected_top: list[str] = []
        works: list[Work] = []

        for pos, i in enumerate(top_positions):
            entry = flat[i]
            title = entry.title
            if title not in expected_set:
                if (title in known_apparatus_titles or is_section_divider(title)
                        or is_other_author_apparatus(title)):
                    continue
                unexpected_top.append(title)
                continue

            found.append(title)
            next_top = top_positions[pos + 1] if pos + 1 < len(top_positions) else len(flat)
            body_parts: list[str] = []
            for child_idx in range(i + 1, next_top):
                child = flat[child_idx]
                if (child.title in universal_exclude_children
                        or (title, child.title) in exclude_child_pairs):
                    continue
                end_href = flat[child_idx + 1].href if child_idx + 1 < len(flat) else None
                start = spine_index[child.href]
                end = spine_index[end_href] if end_href is not None else len(spine)
                for href in spine[start:end]:
                    html = zf.read(f"OEBPS/{href}").decode("utf-8", errors="replace")
                    chunk = _html_to_text(html)
                    if chunk:
                        body_parts.append(chunk)
            works.append(Work(title=title, text="\n\n".join(body_parts), kind="work"))

    missing = [t for t in expected_works if t not in found]
    return ExtractResult(works=works, found=found, missing=missing, unexpected_top=unexpected_top)
