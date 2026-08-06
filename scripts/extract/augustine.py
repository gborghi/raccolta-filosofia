# scripts/extract/augustine.py
"""Adapter bespoke per Agostino d'Ippona. Fonte: epub 'The Complete Works of
St. Augustine' (Patristic Publishing, 2019) - una ricompilazione Calibre della
serie ottocentesca *Nicene and Post-Nicene Fathers, First Series* (NPNF1),
a cura di Philip Schaff, 8 volumi 1886-1890.

PROVENIENZA (verificata leggendo l'epub, non assunta):
- text/part0000.html (frontespizio): "The Collected Works of St. Augustine /
  Philip Schaff / Copyright (C) 2019 Patristic Publishing ... This material is
  available in the public domain." L'editore 2019 dichiara egli stesso PD: la
  ricompilazione (cross-link ai versetti, note in linea) e' lavoro meccanico,
  non un'opera derivata protetta - stesso principio gia' usato per Aquinas
  (ristampa Benziger su testo CCEL PD) e Nietzsche/Descartes (boilerplate di
  un'edizione recente non protegge un testo gia' PD).
- Le intestazioni di sezione ("NPNF1-01. The Confessions and Letters of St.
  Augustine, with a Sketch of his Life and Work") identificano la serie Schaff.
  Traduttori vittoriani, tutti morti da oltre un secolo (Pilkington per le
  Confessioni, Marcus Dods per la Citta' di Dio, Holmes/Wallis per gli
  antipelagiani...): pubblicazione pre-1928, testo abbondantemente PD.
- pd_year=1890 = completamento della serie (gia' PD). traduttore=None a
  livello di Source: la serie mescola molti traduttori, la provenienza sta in
  `edizione`, come per Aristotle/Plato.

STRUTTURA VERA (verificata leggendo toc.ncx e lo spine dell'OPF):
- Il toc.ncx e' PIATTO: 29 navPoint di primo livello, ognuno ancorato al file
  d'inizio di un'opera nello spine. I primi due sono apparato di Schaff e si
  scartano:
    'Prolegomena: St. Augustin's Life And Work'  (biografia del curatore)
    'Chief Events In The Life Of St. Augustin'   (cronologia del curatore)
  Restano 27 opere pubblicabili (EXPECTED_WORKS).
- Ogni opera e' spalmata su MOLTI file part####.html sequenziali (un file per
  capitolo/lettera/salmo, spesso spezzato da Calibre in _split_000/_split_001).
  Il confine di un'opera e' [inizio navPoint i, inizio navPoint i+1) nello
  spine.
- DOPO l'ultima opera ('Expositions On The Book Of Psalms') lo spine prosegue
  con ~928 file di CROSS-REFERENCE BIBLICI (titolo '<Libro> <capitolo>', es.
  'Romans 13', 'Psalms 150') a cui i link in linea puntano: NON sono testo di
  Agostino. Il confine dell'ultima opera e' quindi il primo file biblico, non
  la fine dello spine (bible_start).

PULIZIA DEL TESTO:
- Gli <a> in linea sono SOLO note a pie' di pagina (marcatori tipo [118]) e
  rimandi scritturali (es. '(Ps. cxlv. 3)'): apparato del curatore. Il parser
  scarta l'intero sottoalbero <a>, poi si ripuliscono le parentesi orfane
  rimaste ('( , and . )' -> nulla).
- Pagine di sola navigazione/apparato interne all'opera si saltano per titolo
  (<title> che finisce per 'contents' o contiene 'footnotes') o per
  intestazione (prefazioni del traduttore/curatore, saggi introduttivi). Il
  CONTENTS d'opera NON serve all'atomizzatore qui (niente riga 'CONTENTS'
  letterale come nei Delphi), quindi si scarta: e' pura navigazione.
- I paragrafi si de-wrappano a riga singola (stile del corpus, verificato sui
  _raw Delphi esistenti): un paragrafo = una riga, riga vuota fra paragrafi.
"""
from __future__ import annotations

import glob
import os
import re
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from .common import Work
from .sources import RAW_ROOT, Source

# Cartella sorgente (una sola macchina, come RAW_ROOT): sovrascrivibile via env.
AUGUSTINE_EPUB_DIR = os.environ.get(
    "AUGUSTINE_EPUB_DIR",
    "/Users/g.borghi/Library/CloudStorage/Dropbox/remotedir/libri/"
    "libri_svago/Saggi/spiritualita_cristiana/Sant_Agostino",
)

EXPECTED_WORKS = 27

# I due navPoint d'apparato in testa al toc.ncx (biografia + cronologia del
# curatore Schaff): riconosciuti per prefisso del titolo, non per posizione,
# cosi' un riordino del TOC non li fa passare per opere.
APPARATUS_NAV_PREFIXES = ("prolegomena", "chief events")

# File di solo apparato/navigazione DENTRO un'opera, riconosciuti dal <title>.
_TITLE_SKIP = ("contents", "footnotes")
# ... o dalla prima intestazione del corpo (prefazioni e saggi del curatore).
_HEADING_SKIP = re.compile(
    r"^(translator.?s preface|editor.?s preface|prefatory (note|notice)|"
    r"introductory (essay|notice)|preface)\b",
    re.I,
)

# Un file e' un cross-reference biblico (non Agostino) se il suo <title> e'
# '<Libro> <numero>'. Elenco dei libri (con deuterocanonici, presenti nella
# Vulgata che Agostino cita).
_BIBLE_BOOKS = frozenset(
    """Genesis Exodus Leviticus Numbers Deuteronomy Joshua Judges Ruth Samuel
    Kings Chronicles Ezra Nehemiah Esther Job Psalms Psalm Proverbs Ecclesiastes
    Song Isaiah Jeremiah Lamentations Ezekiel Daniel Hosea Joel Amos Obadiah
    Jonah Micah Nahum Habakkuk Zephaniah Haggai Zechariah Malachi Matthew Mark
    Luke John Acts Romans Corinthians Galatians Ephesians Philippians Colossians
    Thessalonians Timothy Titus Philemon Hebrews James Peter Jude Revelation
    Wisdom Sirach Ecclesiasticus Tobit Judith Baruch Maccabees Esdras""".split()
)
_BIBLE_TITLE = re.compile(r"^(?:[1-3]\s+)?([A-Z][a-z]+)(?:\s+of\s+\w+)?\s+\d+$")

_SMALL_WORDS = {"of", "and", "the", "on", "in", "to", "a", "an", "for",
                "with", "by", "his", "of", "upon"}


def _titlecase(s: str) -> str:
    """Le navLabel del NCX hanno maiuscole a casaccio ('City Of God'): le
    parole brevi tornano minuscole (tranne la prima)."""
    words = s.split()
    out = []
    for k, w in enumerate(words):
        low = w.lower()
        out.append(low if (k > 0 and low in _SMALL_WORDS) else w)
    return " ".join(out)


class _Extractor(HTMLParser):
    """<body> -> paragrafi puliti. Scarta il sottoalbero <a> (note/rimandi
    scritturali). Un blocco (p, h1-6, li, blockquote) = un paragrafo, con gli
    a-capo interni della fonte collassati a spazio (de-wrap)."""

    _BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"}
    _DROP = {"a"}  # sottoalbero scartato per intero

    def __init__(self) -> None:
        super().__init__()
        self._in_body = False
        self._drop_depth = 0
        self._paras: list[str] = []
        self._cur: list[str] = []

    def _flush(self) -> None:
        if self._cur:
            para = re.sub(r"\s+", " ", "".join(self._cur)).strip()
            if para:
                self._paras.append(para)
            self._cur = []

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self._in_body = True
            return
        if not self._in_body:
            return
        if tag in self._DROP:
            self._drop_depth += 1
            return
        if self._drop_depth:
            return
        if tag in self._BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag == "body":
            self._in_body = False
            return
        if not self._in_body:
            return
        if tag in self._DROP and self._drop_depth:
            self._drop_depth -= 1
            return
        if self._drop_depth:
            return
        if tag in self._BLOCK:
            self._flush()

    def handle_data(self, data):
        if self._in_body and not self._drop_depth:
            self._cur.append(data)

    def paragraphs(self) -> list[str]:
        self._flush()
        return self._paras


# Parentesi/quadre orfane lasciate dallo scarto degli <a> (rimandi scritturali
# e marcatori di nota): '( , and . )', '[ ]', spazi prima di punteggiatura.
_ORPHAN_PAREN = re.compile(r"\(\s*(?:[.,;:]|and|&|\s)*\s*\)")
_ORPHAN_BRACK = re.compile(r"\[\s*(?:[.,;:]|\s)*\s*\]")
# Marcatore di nota rimasto come testo nudo (non era dentro un <a>): parentesi
# quadra con dentro solo un numero, es. '[3415]'. La prosa tradotta di Agostino
# non contiene mai numeri isolati fra quadre: sono sempre rimandi di nota.
_FOOTNOTE_NUM = re.compile(r"\[\s*\d{1,6}\s*\]")
_SPACE_PUNCT = re.compile(r"\s+([.,;:!?])")
_MULTISPACE = re.compile(r"[ \t]{2,}")


def _clean(text: str) -> str:
    text = _FOOTNOTE_NUM.sub("", text)
    text = _ORPHAN_PAREN.sub("", text)
    text = _ORPHAN_BRACK.sub("", text)
    text = _SPACE_PUNCT.sub(r"\1", text)
    text = _MULTISPACE.sub(" ", text)
    return text.strip()


@dataclass
class _Nav:
    title: str
    href: str  # file spine relativo (senza ancora)


@dataclass
class ExtractResult:
    works: list[Work]
    toc_titles: list[str] = field(default_factory=list)
    skipped_files: int = 0


def find_epub(source: Source) -> Path:
    """L'epub inglese (NPNF), MAI la Confessioni italiana Garzanti (in
    copyright) che vive nella stessa cartella. Si sceglie per nome: il file
    inglese contiene 'Complete Works'."""
    for d in (AUGUSTINE_EPUB_DIR, os.path.join(RAW_ROOT, "augustine"), RAW_ROOT):
        cands = sorted(glob.glob(os.path.join(d, "*.epub")))
        english = [c for c in cands if "complete works" in os.path.basename(c).lower()]
        if english:
            return Path(english[0])
    raise FileNotFoundError(
        f"epub 'Complete Works of St. Augustine' non trovato in {AUGUSTINE_EPUB_DIR}"
    )


def _opf_dir_and_spine(zf: zipfile.ZipFile) -> tuple[str, list[str]]:
    """(prefisso cartella dell'OPF, lista file dello spine in ordine)."""
    container = zf.read("META-INF/container.xml").decode("utf-8")
    opf_path = re.search(r'full-path="([^"]+)"', container).group(1)
    opf_dir = os.path.dirname(opf_path)
    opf = zf.read(opf_path).decode("utf-8")
    manifest = dict(re.findall(r'<item id="([^"]+)"[^>]*href="([^"]+)"', opf))
    # gli attributi possono essere in ordine diverso: secondo tentativo
    if not manifest:
        manifest = dict(
            (re.search(r'id="([^"]+)"', it).group(1),
             re.search(r'href="([^"]+)"', it).group(1))
            for it in re.findall(r"<item\b[^>]*/?>", opf)
            if re.search(r'id="', it) and re.search(r'href="', it)
        )
    ids = re.findall(r'<itemref[^>]*idref="([^"]+)"', opf)
    spine = [manifest[i] for i in ids if i in manifest]
    return opf_dir, spine


def _read_ncx(zf: zipfile.ZipFile, opf_dir: str) -> list[_Nav]:
    ncx_name = next(n for n in zf.namelist() if n.lower().endswith(".ncx"))
    x = zf.read(ncx_name).decode("utf-8")
    ns = {"n": "http://www.daisy.org/z3986/2005/ncx/"}
    root = ET.fromstring(x)
    navs: list[_Nav] = []
    for np in root.find("n:navMap", ns).findall("n:navPoint", ns):
        label = np.find("n:navLabel/n:text", ns).text or ""
        src = np.find("n:content", ns).get("src", "")
        href = src.split("#", 1)[0]
        navs.append(_Nav(re.sub(r"\s+", " ", label).strip(), href))
    return navs


def _join(opf_dir: str, href: str) -> str:
    return f"{opf_dir}/{href}" if opf_dir else href


def _title_of(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _headings(html: str) -> list[str]:
    """Tutte le intestazioni del file (non solo la prima): il file-frontespizio
    di un'opera porta prima l'occhiello ('St. Aurelius Augustin') e SOLO PIU'
    IN BASSO l'intestazione d'apparato ('Translator's Preface') - guardare solo
    la prima lo lascerebbe passare per testo d'autore."""
    return [
        re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", m)).strip()
        for m in re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", html, re.S)
    ]


def _is_bible(title: str) -> bool:
    m = _BIBLE_TITLE.match(title)
    return bool(m and m.group(1) in _BIBLE_BOOKS)


def _is_apparatus_file(title: str, headings: list[str]) -> bool:
    t = title.lower()
    if t.endswith("contents") or "footnotes" in t:
        return True
    return any(_HEADING_SKIP.match(h) for h in headings)


def extract(epub_path: Path) -> ExtractResult:
    with zipfile.ZipFile(epub_path) as zf:
        opf_dir, spine = _opf_dir_and_spine(zf)
        navs = _read_ncx(zf, opf_dir)

        # indice di ogni file-spine, per mappare gli href del NCX a posizioni.
        pos = {href: k for k, href in enumerate(spine)}

        # confine biblico: primo file dello spine il cui <title> e' '<Libro> N'.
        bible_start = len(spine)
        for k, href in enumerate(spine):
            full = _join(opf_dir, href)
            try:
                html = zf.read(full).decode("utf-8", "replace")
            except KeyError:
                continue
            if _is_bible(_title_of(html)):
                bible_start = k
                break

        # opere pubblicabili: navPoint non-apparato, con inizio nello spine.
        works_nav = [
            n for n in navs
            if not n.title.lower().startswith(APPARATUS_NAV_PREFIXES)
            and n.href in pos and pos[n.href] < bible_start
        ]
        if len(works_nav) != EXPECTED_WORKS:
            raise ValueError(
                f"attese {EXPECTED_WORKS} opere, trovati {len(works_nav)} "
                f"navPoint pubblicabili: {[n.title for n in works_nav]}"
            )

        starts = [pos[n.href] for n in works_nav]
        bounds = starts[1:] + [bible_start]

        works: list[Work] = []
        skipped = 0
        for n, lo, hi in zip(works_nav, starts, bounds):
            paras: list[str] = []
            for k in range(lo, hi):
                full = _join(opf_dir, spine[k])
                try:
                    html = zf.read(full).decode("utf-8", "replace")
                except KeyError:
                    continue
                if _is_apparatus_file(_title_of(html), _headings(html)):
                    skipped += 1
                    continue
                ex = _Extractor()
                ex.feed(html)
                for p in ex.paragraphs():
                    p = _clean(p)
                    if p:
                        paras.append(p)
            text = "\n\n".join(paras)
            if not text.strip():
                raise ValueError(f"opera vuota dopo la pulizia: {n.title!r}")
            works.append(Work(title=_titlecase(n.title), text=text, kind="work"))

    return ExtractResult(works=works,
                         toc_titles=[n.title for n in works_nav],
                         skipped_files=skipped)
