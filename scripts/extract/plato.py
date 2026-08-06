# scripts/extract/plato.py
"""Adapter bespoke per Platone. Fonte: un solo file .epub inglese (Delphi
Classics 2012, "Complete Works of Plato (Illustrated)"), copiato in
RAW_ROOT/plato/ dall'originale in
.../libri_svago/Saggi/filosofia/platone-aristotele/ (cartella condivisa con
l'epub gemello di Aristotele: la separazione per cartella, non un filtro sul
nome, e' cio' che garantisce che questo adapter non tocchi mai l'epub di
Aristotele). NON e' un blob .txt come i Delphi via grouptxt: si apre con
zipfile e si legge OEBPS/toc.ncx.

TOC verificato a mano (265 navPoint totali, non 265 dialoghi): struttura a
2 livelli sotto ogni voce top-level ("The Translations", poi "The Spurious
Works", poi "The Epistles", poi "The Greek Texts", poi apparato biografico/
critico/catalogo). Ogni dialogo appare nel TOC come contenitore top-level
(depth 0) il cui href punta NON al testo di Platone ma a una sinossi in
terza persona scritta dal curatore ("Translated by Benjamin Jowett This is
one of Plato's earliest dialogues, which is..." -- guardacaso la stessa voce
di menu del testo vero, stesso titolo, contenuto diverso). Sotto, come figli
depth 1, compaiono in ordine variabile: CONTENTS (indice), INTRODUCTION.
(saggio critico di Jowett, terza persona, spesso 10-90k caratteri), ARGUMENT/
CHARACTERS/THE INTRODUCTION (solo per Repubblica), ENDNOTES. (note a fine
dialogo) -- tutto apparato -- e infine UNA voce con testo di Platone vero
("PERSONS OF THE DIALOGUE: ..."). Per Repubblica e Leggi il "vero testo" e'
diviso in piu' voci BOOK I..BOOK X/XII, tutte da concatenare.

Insidia in piu' rispetto a Nietzsche: alcuni dialoghi (HIPPIAS MAJOR, LACHES,
CRATYLUS, MINOS, SISYPHUS, ERYXIAS, SECOND ALCIBIADES, EPIGRAMS...) non hanno
NESSUNA voce-figlia nel TOC: il loro testo vero e' un file nello spine subito
dopo la sinossi, mai referenziato da toc.ncx. Non si puo' quindi camminare il
solo TOC (come nietzsche.py): bisogna leggere l'HTML di ogni file nel range
[src_del_contenitore, src_del_contenitore_successivo) e classificarlo dal
markup, non dal solo titolo:
  - <h1> in testa al body = sinossi del contenitore -> sempre apparato
    (e' sempre il primo file del range, essendo l'href del navPoint stesso).
  - <h2> in testa al body = intestazione esplicita di sotto-sezione. Se il
    testo normalizzato e' nel vocabolario chiuso APPARATUS_HEADINGS -> scarta.
    Se e' "BOOK <romano>" -> e' testo di Platone (Repubblica/Leggi). Qualsiasi
    altra intestazione h2 -> e' il titolo del dialogo vero -> comincia il
    corpo pubblicabile.
  - Un <p> il cui UNICO contenuto (dopo gli <a id> di ancora) e' uno <span>
    breve = stesso ruolo di un <h2>, usato da Delphi per i dialoghi orfani
    di voce TOC (verificato leggendo il markup grezzo di HIPPIAS MAJOR e
    LACHES: "<p class='p27'><a id=...></a><span class='t21'>LACHES</span></p>",
    stessa forma della sinossi/caption ma SENZA blocco immagine davanti).
  - Un <p> il cui primo figlio e' un'immagine (<img>) = didascalia/figura,
    mai contenuto: scartato sempre, indipendentemente dallo stato corrente
    (nessuna immagine e' mai stata trovata dopo l'inizio del corpo vero in
    nessuno dei ~30 dialoghi ispezionati a mano, ma il controllo resta
    esplicito per sicurezza).
  - Nessuno dei precedenti (paragrafo che comincia gia' con prosa, nessuna
    ancora <a id> davanti) = pagina di continuazione: eredita lo stato del
    file precedente (i dialoghi lunghi -- Repubblica, Leggi, Timeo, Sofista,
    Fedro... -- proseguono su piu' file senza una nuova intestazione a ogni
    file).

Traduttore verificato leggendo la riga "Translated by X" di OGNI sinossi,
non solo della prima (richiesto esplicitamente): Delphi mescola CINQUE
traduttori in questo epub. Solo Jowett (morto 1893, PD) e' incluso:
  - William R.M. Lamb: HIPPARCHUS, THE RIVAL LOVERS, THEAGES, MINOS,
    EPINOMIS -- traduzioni Loeb Classical Library (Lamb morto 1958,
    Loeb/Harvard University Press, rischio copyright reale, non "gia' PD"
    come Jowett) -> ESCLUSI.
  - R. G. Bury: The Epistles (le 13 lettere) -- altra traduzione Loeb
    (Bury morto 1951) -> ESCLUSE.
  - George Burges (traduttore ottocentesco Bohn's Classical Library, PD ma
    NON e' il traduttore dichiarato nella Source "Benjamin Jowett"): CLITOPHON,
    SISYPHUS, AXIOCHUS, DEMODOCUS, ON JUSTICE, ON VIRTUE (+ DEFINITIONS,
    apparato annesso a ON VIRTUE) -> ESCLUSI (traduttore diverso da quello
    dichiarato, anche se probabilmente PD: la Source qui ha un solo campo
    traduttore, non uno per opera).
  - George Pallatos (traduttore non verificabile, data ignota): HALCYON,
    EPIGRAMS -> ESCLUSI.
  - Robert Drew Hicks: solo nell'apparato biografico (Diogenes Laertius),
    gia' escluso in quanto biografia, non opera di Platone.
LACHES e' un'eccezione: la sua sinossi (text00033.html) e' l'UNICA priva
della riga "Translated by X" (verificato leggendo l'HTML grezzo). Incluso
comunque: Laches fa parte del corpus di Jowett fin dalla prima edizione
delle sue "Dialogues of Plato" (1871/1892) e nessun altro traduttore e'
accreditato da nessuna parte per questo dialogo in questo epub -- l'assenza
di credito e' letta come una svista editoriale di Delphi sulla sinossi, non
come "traduttore ignoto". Il testo vero di Laches (text00036.html, verificato
a mano) e' comunque prosa in prima/terza persona coerente con lo stile
Jowett, nessun segnale di traduzione diversa.

"The Greek Texts" (testo originale greco, stessi 28 dialoghi) e' escluso per
lingua (Source.lang="en", non e' una traduzione). "The Criticism", "The
Biographies", "The Delphi Classics Catalogue" sono apparato/opere di altri
autori su Platone, mai di Platone: esclusi a monte per titolo di sezione.
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
_SRC_RE = re.compile(r"^text(\d{5})\.html")
_FILE_RE = re.compile(r"^OEBPS/text(\d{5})\.html$")
_BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "br"}

# Le 30 opere effettivamente tradotte da Jowett (vedi docstring modulo per
# la verifica traduttore-per-traduttore). Ordine = ordine nel TOC. Elenco
# chiuso, fail-closed come cartesio.EXPECTED_WORKS: qualunque voce top-level
# nello scope "dialoghi" che non sia ne' qui ne' in _OTHER_TRANSLATORS fa
# fallire l'estrazione invece di essere ignorata silenziosamente.
EXPECTED_JOWETT_DIALOGUES: list[str] = [
    "EUTHYPHRO", "APOLOGY", "CRITO", "HIPPIAS MAJOR", "HIPPIAS MINOR",
    "FIRST ALCIBIADES", "CHARMIDES", "LACHES", "LYSIS", "ION", "PHAEDO",
    "CRATYLUS", "EUTHYDEMUS", "PROTAGORAS", "GORGIAS", "MENO", "MENEXENUS",
    "SYMPOSIUM", "THE REPUBLIC", "PHAEDRUS", "PARMENIDES", "THEAETETUS",
    "TIMAEUS", "CRITIAS", "SOPHIST", "STATESMAN", "PHILEBUS", "LAWS",
    "SECOND ALCIBIADES", "ERYXIAS",
]

# Dialoghi nello stesso scope (The Translations / The Spurious Works) ma
# tradotti da qualcun altro: esclusi. Vedi docstring modulo per la fonte di
# ogni riga (letta dalla sinossi di ciascuno, non assunta).
OTHER_TRANSLATORS: dict[str, str] = {
    "CLITOPHON": "George Burges",
    "HIPPARCHUS": "W.R.M. Lamb",
    "THE RIVAL LOVERS": "W.R.M. Lamb",
    "THEAGES": "W.R.M. Lamb",
    "MINOS": "W.R.M. Lamb",
    "EPINOMIS": "W.R.M. Lamb",
    "SISYPHUS": "George Burges",
    "AXIOCHUS": "George Burges",
    "DEMODOCUS": "George Burges",
    "HALCYON": "George Pallatos",
    "ON JUSTICE": "George Burges",
    "ON VIRTUE": "George Burges",
    "EPIGRAMS": "George Pallatos",
}

# "The Spurious Works" e' il divisore di sotto-sezione dentro lo scope
# (compare come voce top-level tra i dialoghi genuini e quelli spuri, con un
# proprio file-sinossi senza contenuto di Platone: "The ancient Agora,
# Athens" + un'immagine). Non e' un dialogo, non e' un'esclusione per
# traduttore: va solo saltato, senza contare ne' come trovato ne' come
# inatteso.
_SECTION_DIVIDERS = frozenset({"The Spurious Works"})

# Le tre sezioni top-level che delimitano lo scope "dialoghi attribuiti a
# Platone" (The Translations + The Spurious Works). Tutto cio' che segue
# "The Epistles" (Epistole, testi greci, critica, biografie, catalogo) resta
# fuori scope a prescindere dal traduttore.
_SCOPE_START_SECTION = "The Translations"
_SCOPE_END_SECTION = "The Epistles"

# Intestazioni (h2, o paragrafo-titolo equivalente) che sono SEMPRE apparato.
# Vocabolario chiuso: qualunque intestazione non riconosciuta e non "BOOK
# <romano>" viene trattata come inizio del testo vero (vedi _classify_page),
# quindi un errore qui rischierebbe di pubblicare apparato -- ogni voce e'
# stata vista almeno una volta nell'HTML grezzo durante la ricognizione.
APPARATUS_HEADINGS = frozenset({
    "INTRODUCTION", "INTRODUCTION AND ANALYSIS", "CONTENTS", "ENDNOTES",
    "ARGUMENT", "CHARACTERS", "THE INTRODUCTION", "ON THE IDEAS OF PLATO",
    "EXCURSUS ON THE RELATION OF THE LAWS OF PLATO TO THE INSTITUTIONS OF "
    "CRETE AND LACEDAEMON",
})
_BOOK_RE = re.compile(r"^BOOK [IVXLCM]+$")

# Prima riga da scartare quando coincide col titolo appena classificato: la
# riga h2/paragrafo-titolo che ha fatto scattare "inizio corpo" finisce
# comunque nel testo estratto (stesso file), e duplicherebbe l'heading "#
# {title}" gia' scritto da common.render. Non si applica alle intestazioni
# "BOOK <romano>" (Repubblica/Leggi): quelle sono marcatori strutturali utili
# nel corpo, non un doppione del titolo del dialogo.
_HEAD_LINE_RE = re.compile(r"^[ \t]*\S.*$", re.MULTILINE)


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
class _Top:
    title: str
    fnum: int


def _parse_top_level(zf: zipfile.ZipFile) -> list[_Top]:
    """Solo le voci depth 0 del TOC (i contenitori): bastano per calcolare i
    range di file da esaminare. I figli depth 1 non si usano per delimitare
    il corpo (troppi dialoghi non ne hanno) -- solo per il conteggio di
    verifica in run.py."""
    ncx = ET.fromstring(zf.read("OEBPS/toc.ncx"))
    navmap = ncx.find(f"{NCX_NS}navMap")
    if navmap is None:
        raise ValueError("toc.ncx senza navMap")
    tops: list[_Top] = []
    for nav in navmap.findall(f"{NCX_NS}navPoint"):
        label = nav.find(f"{NCX_NS}navLabel/{NCX_NS}text")
        content = nav.find(f"{NCX_NS}content")
        if label is None or content is None:
            continue
        m = _SRC_RE.match(content.get("src", ""))
        if m is None:
            raise ValueError(f"voce TOC top-level con href inatteso: {content.get('src')!r}")
        tops.append(_Top(title=(label.text or "").strip(), fnum=int(m.group(1))))
    if not tops:
        raise ValueError("toc.ncx senza navPoint top-level: formato cambiato")
    return tops


def count_navpoints(zf: zipfile.ZipFile) -> int:
    ncx = ET.fromstring(zf.read("OEBPS/toc.ncx"))
    return sum(1 for _ in ncx.iter(f"{NCX_NS}navPoint"))


class _BodyTextExtractor(HTMLParser):
    """Estrae testo nudo dal <body>. converts_charrefs=True (default in
    Python 3): le entita' HTML arrivano gia' decodificate a handle_data."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._in_body = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "body":
            self._in_body = True
            return
        if self._in_body and tag in _BLOCK_TAGS:
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


_BODY_RE = re.compile(r"<body\b[^>]*>(.*)</body>", re.S | re.I)
_FIRST_BLOCK_RE = re.compile(r"\s*<(h1|h2|p)\b[^>]*>(.*?)</\1>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_LEADING_ANCHORS_RE = re.compile(r"^(?:\s*<a\b[^>]*>.*?</a>)*", re.S | re.I)
# Un paragrafo-titolo e' un <p> il cui UNICO contenuto (dopo eventuali <a id>
# di ancora, presenti solo se qualcos'altro nell'epub punta li') e' un solo
# <span>...</span>: mai testo libero. Verificato confrontando CRATYLUS
# (nessuna ancora, "<p class='p27'><span>CRATYLUS.</span></p>") con LACHES
# (ancora presente, stessa forma altrimenti): l'ancora NON e' un segnale
# affidabile, la forma "tutto lo span e nient'altro" si'.
_SPAN_ONLY_RE = re.compile(r"^\s*<span\b[^>]*>(.*?)</span>\s*$", re.S | re.I)


def _strip_tags(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html)).strip()


def _normalize_heading(text: str) -> str:
    # Alcuni <span> hanno un a-capo tra la parola e il punto finale (es.
    # "INTRODUCTION\n." in EUTHYDEMUS, text00058.html): rstrip(".") da solo
    # lascerebbe uno spazio finale che rompe il confronto col vocabolario
    # chiuso ("INTRODUCTION " != "INTRODUCTION"), quindi un secondo strip()
    # dopo aver tolto i punti.
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed.rstrip(".").strip().upper()


def _classify_page(html: str) -> tuple[str, str]:
    """Ritorna (kind, extracted_text). kind e' uno tra:
    "apparatus" (sinossi h1 o intestazione h2/paragrafo nel vocabolario
    chiuso: scartare, senza cambiare lo stato precedente se e' un file di
    continuazione -- ma un'intestazione riconosciuta CAMBIA sempre lo stato),
    "book" (BOOK <romano>: testo di Platone, marcatore da conservare),
    "title" (intestazione non riconosciuta: comincia il testo vero, la riga
    di intestazione va scartata perche' duplica l'heading gia' scritto),
    "image" (didascalia/figura: scarta sempre, non cambia stato),
    "continue" (pagina di continuazione, nessuna intestazione: eredita lo
    stato precedente)."""
    body_m = _BODY_RE.search(html)
    inner = body_m.group(1) if body_m else html
    first_m = _FIRST_BLOCK_RE.match(inner)
    text = _html_to_text(html)
    if first_m is None:
        return "continue", text
    tag, content = first_m.group(1).lower(), first_m.group(2)
    if tag == "h1":
        return "apparatus", text
    if tag == "h2":
        heading = _normalize_heading(_strip_tags(content))
        if heading in APPARATUS_HEADINGS:
            return "apparatus", text
        if _BOOK_RE.match(heading):
            return "book", text
        return "title", text
    # tag == "p": tre casi -- immagine, paragrafo-titolo (solo uno <span>,
    # nessun'altra prosa, ancora opzionale), o prima riga di prosa vera
    # (continuazione).
    if re.search(r"<img\b", content, re.I):
        return "image", text
    after_anchors = _LEADING_ANCHORS_RE.sub("", content, count=1)
    span_m = _SPAN_ONLY_RE.match(after_anchors)
    if span_m is not None:
        stripped = _strip_tags(span_m.group(1))
        if stripped and len(stripped) <= 120:
            heading = _normalize_heading(stripped)
            if heading in APPARATUS_HEADINGS:
                return "apparatus", text
            if _BOOK_RE.match(heading):
                return "book", text
            return "title", text
    return "continue", text


def _drop_leading_heading_line(text: str) -> str:
    """Rimuove la prima riga non vuota (l'intestazione appena classificata
    come "title"): resta solo il testo di Platone, senza duplicare
    l'heading "# {title}" gia' scritto da common.render."""
    lines = text.split("\n", 1)
    if len(lines) == 1:
        return ""
    return lines[1].strip()


@dataclass
class ExtractResult:
    works: list[Work] = field(default_factory=list)
    toc_titles: list[str] = field(default_factory=list)
    unexpected: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def extract(epub_path: Path) -> ExtractResult:
    with zipfile.ZipFile(epub_path) as zf:
        tops = _parse_top_level(zf)
        by_title = {t.title: t for t in tops}
        if _SCOPE_START_SECTION not in by_title or _SCOPE_END_SECTION not in by_title:
            raise ValueError(
                f"sezioni di scope non trovate nel TOC: "
                f"{_SCOPE_START_SECTION!r} / {_SCOPE_END_SECTION!r}"
            )
        start = tops.index(by_title[_SCOPE_START_SECTION])
        end = tops.index(by_title[_SCOPE_END_SECTION])
        scope = tops[start + 1:end]  # tutti i dialoghi (genuini + spuri)

        unexpected: list[str] = []
        found: list[str] = []
        works: list[Work] = []

        for i, top in enumerate(scope):
            if top.title in _SECTION_DIVIDERS:
                continue
            if top.title in OTHER_TRANSLATORS:
                continue
            if top.title not in EXPECTED_JOWETT_DIALOGUES:
                unexpected.append(top.title)
                continue
            found.append(top.title)
            next_fnum = scope[i + 1].fnum if i + 1 < len(scope) else tops[end].fnum
            state = "apparatus"
            body_parts: list[str] = []
            for fnum in range(top.fnum, next_fnum):
                fname = f"OEBPS/text{fnum:05d}.html"
                try:
                    html = zf.read(fname).decode("utf-8", errors="replace")
                except KeyError:
                    continue
                kind, text = _classify_page(html)
                if kind == "image":
                    continue
                if kind == "apparatus":
                    state = "apparatus"
                    continue
                if kind == "book":
                    state = "body"
                    if text:
                        body_parts.append(text)
                    continue
                if kind == "title":
                    state = "body"
                    trimmed = _drop_leading_heading_line(text)
                    if trimmed:
                        body_parts.append(trimmed)
                    continue
                # kind == "continue": eredita lo stato del file precedente.
                if state == "body" and text:
                    body_parts.append(text)
            works.append(Work(title=top.title, text="\n\n".join(body_parts), kind="work"))

        missing = [t for t in EXPECTED_JOWETT_DIALOGUES if t not in found]
    return ExtractResult(works=works, toc_titles=[t.title for t in tops],
                          unexpected=unexpected, missing=missing)
