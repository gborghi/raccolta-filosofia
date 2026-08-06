# scripts/extract/aristotle.py
"""Adapter bespoke per Aristotele. Fonte: un solo file .epub inglese (Delphi
Classics 2013, traduzioni ottocentesche/primo-Novecento PD). Come nietzsche.py
(il modello più vicino) si apre con zipfile e si legge il TOC (qui root
"toc.ncx", non "OEBPS/toc.ncx": questo epub non ha la cartella OEBPS) per
sapere quali navPoint sono opere pubblicabili.

A differenza di Nietzsche, qui il TOC NON è "tutto opere": è un indice a due
livelli appiattito (63 navPoint) che mescola:
  - 7 intestazioni di SEZIONE (LOGIC, PHYSICS, METAPHYSICS, ETHICS AND
    POLITICS, RHETORIC AND POETICS, "The Translations", "The Parva
    Naturalia") — mai testo di Aristotele, sempre o un titolo nudo o, per
    "The Parva Naturalia", un sommario editoriale con l'elenco dei 7
    trattati contenuti;
  - 46 opere vere (verificate leggendo il testo reale di ognuna, non solo il
    titolo — vedi ricerca in sessione: ogni pagina-navpoint è stata aperta e
    ispezionata);
  - 10 voci di apparato Delphi dopo "The Greek Texts" (testo greco a fronte,
    guida di pronuncia, 4 biografie/saggi su Aristotele scritti da altri
    autori — Diogene Laerzio, Hubbard, McRae, Davidson, MacGillivray — e il
    catalogo pubblicitario Delphi).

Ogni pagina-navpoint di un'opera vera è: <h1>Titolo (Bekker)</h1>, spesso
un'iconcina decorativa, poi "Translated by X" (il traduttore, diverso per
quasi ogni opera: verificato leggendo la riga reale, mai assunto), e infine
o subito il testo di Aristotele o 1-2 paragrafi di blurb editoriale Delphi
("This treatise is...", in terza persona, a volte con un elenco tipo indice)
prima del corpo vero. Il confine blurb/corpo è quasi sempre marcato da un
<h2>CONTENTS</h2> strutturale (indice interno dei Book/Part/Section
dell'opera, generato da Delphi ma che riproduce la struttura originale — si
tiene, come il "CONTENTS" di Seneca). Le 13 opere senza CONTENTS sono
elencate esplicitamente in NO_CONTENTS_MARKER sotto, verificate a mano
leggendo il testo pagina per pagina.

Didascalie di immagini (ritratti, buste, manoscritti — MAI testo di
Aristotele) hanno una firma HTML fissa e verificata: un <p> che contiene
SOLO un <img>, seguito immediatamente da un <p> il cui intero contenuto è
avvolto in <span class="italic">. Coppie così fatte vengono scartate ovunque
compaiano nell'intervallo di un'opera (non solo in testa): i ritratti di
filosofi terzi citati nel corpo (es. Parmenide dentro Physics, Teofrasto
dentro On Breath) usano la stessa firma. Un <img> senza didascalia italic
successiva (diagrammi decorativi in mezzo alla prosa, es. la rosa dei venti
in On the Universe) viene invece scartato da solo, lasciando intatta la
prosa intorno: non è mai un carattere che sostituisce testo (a differenza
del caso Nietzsche/greco), qui le lettere greche sono sempre testo Unicode
vero.
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
_PART_RE = re.compile(r"^index_split_(\d{3,4})\.html$")

# Le 7 intestazioni di sezione: mai testo di Aristotele. "The Translations"
# è l'indice generale (analogo a WORK_SECTIONS in delphi_toc.py per i Delphi
# piatti: lì "The Translations" è sezione anch'essa, non opera). "The Parva
# Naturalia" è title-case non maiuscolo come le altre, ma la sua pagina è
# verificata: solo titolo + traduttore-collettivo + elenco dei 7 trattati,
# nessun testo di Aristotele proprio.
SECTION_TITLES = frozenset({
    "The Translations", "LOGIC", "PHYSICS", "The Parva Naturalia",
    "METAPHYSICS", "ETHICS AND POLITICS", "RHETORIC AND POETICS",
})

# Le 10 voci di apparato dopo il corpus filosofico: testo greco a fronte,
# pronuncia, biografie/saggi su Aristotele NON scritti da lui, catalogo
# pubblicitario Delphi. Elencate esplicitamente (vocabolario chiuso, come
# KNOWN_APPARATUS_TITLES in cartesio.py) invece che dedotte da un pattern:
# alcuni di questi titoli (es. "ARISTOTLE by...") assomigliano a titoli di
# opere e non vanno confusi per pattern-matching.
APPARATUS_TITLES = frozenset({
    "The Greek Texts", "PRONOUNCING ANCIENT GREEK", "LIST OF GREEK TEXTS",
    "The Biographies",
    "ARISTOTLE: LIVES OF THE EMINENT PHILOSOPHERS by Diogenes Laërtius",
    "ARISTOTLE by Elbert Hubbard", "ARISTOTLE by Charles McRae",
    "ARISTOTLE AND ANCIENT EDUCATIONAL IDEALS by Thomas Davidson",
    "ARISTOTLE by William MacGillivray", "The Delphi Classics Catalogue",
})

# Le 46 opere pubblicabili, nell'ordine del TOC (7 sezioni + 46 opere + 10
# apparato = 63 navPoint, verificato sul TOC reale). Asserzione esplicita
# (come EXPECTED_WORKS in cartesio.py) invece di dedurle per esclusione:
# una voce del TOC non riconosciuta deve far fallire l'estrazione, non
# scivolare silenziosamente in nessuna delle due categorie.
EXPECTED_WORKS: list[str] = [
    "Categories (1a)",
    "On Interpretation (16a)",
    "Prior Analytics (24a)",
    "Posterior Analytics (71a)",
    "Topics (100a)",
    "Sophistical Refutations (164a)",
    "Physics (184a)",
    "On the Heavens (268a)",
    "On Generation and Corruption (314a)",
    "Meteorology (338a)",
    "On the Universe (391a)",
    "On the Soul (402a)",
    "Sense and Sensibilia (436a)",
    "On Memory (449b)",
    "On Sleep (453b)",
    "On Dreams (458a)",
    "On Divination in Sleep (462b)",
    "On Length and Shortness of Life (464b)",
    "On Youth, Old Age, Life and Death, and Respiration (467b)",
    "On Breath (481a)",
    "History of Animals (486a)",
    "Parts of Animals (639a)",
    "Movement of Animals (698a)",
    "Progression of Animals (704a)",
    "Generation of Animals (715a)",
    "On Colours (791a)",
    "On Things Heard (800a)",
    "Physiognomonics (805a)",
    "On Plants (815a)",
    "On Marvelous Things Heard (830a)",
    "Mechanics (847a)",
    "Problems (859a)",
    "On Indivisible Lines (968a)",
    "The Situations and Names of Winds (973a)",
    "On Melissus, Xenophanes, and Gorgias (974a)",
    "Metaphysics (980a)",
    "Nicomachean Ethics (1094a)",
    "Great Ethics (1181a)",
    "Eudemian Ethics (1214a)",
    "On Virtues and Vices (1249a)",
    "Politics (1252a)",
    "Economics (1343a)",
    "Rhetoric (1354a)",
    "Rhetoric to Alexander (1420a)",
    "Poetics (1447a)",
    "Constitution of the Athenians",
]

# Le 13 opere la cui pagina-navpoint non porta a un <h2>CONTENTS</h2>.
# Verificate a mano leggendo il testo reale (vedi ricerca in sessione):
# "" = nessun blurb Delphi, la riga "Translated by X" è seguita subito dal
# testo di Aristotele (resta nel corpo, come i Delphi piatti quando
# work_starts.json ha first_line=""); un valore non vuoto = il primo blocco
# di testo genuino con cui il corpo comincia DAVVERO — tutto ciò che lo
# precede (compresa la riga "Translated by") è blurb editoriale Delphi e va
# tagliato. "1" per Sophistical Refutations è il numero del primo capitolo
# (il blurb lì è un elenco di fallacie, non testo aristotelico); "ON
# COLOURS"/"MECHANICAL PROBLEMS"/"On Virtues and Vices" sono l'intestazione
# ripetuta con cui il corpo vero e proprio si apre in quelle tre opere,
# dopo un paragrafo di blurb Delphi ("De Coloribus is a treatise
# attributed to...", ecc.) e (per On Colours) una pagina-ritratto.
NO_CONTENTS_MARKER: dict[str, str] = {
    "Sophistical Refutations (164a)": "1",
    "Sense and Sensibilia (436a)": "",
    "On Memory (449b)": "",
    "On Sleep (453b)": "",
    "On Dreams (458a)": "",
    "On Divination in Sleep (462b)": "",
    "On Length and Shortness of Life (464b)": "",
    "On Youth, Old Age, Life and Death, and Respiration (467b)": "",
    "Movement of Animals (698a)": "",
    "Progression of Animals (704a)": "",
    "On Colours (791a)": "ON COLOURS",
    "Mechanics (847a)": "MECHANICAL PROBLEMS",
    "On Virtues and Vices (1249a)": "On Virtues and Vices",
}

_TRANSLATED_BY_RE = re.compile(r"^Translated by\s*[\xa0 ]*(.+)$")


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
class TocEntry:
    title: str
    start_num: int


def _parse_toc(zf: zipfile.ZipFile) -> list[TocEntry]:
    ncx = ET.fromstring(zf.read("toc.ncx"))
    entries: list[TocEntry] = []
    for nav in ncx.iter(f"{NCX_NS}navPoint"):
        label = nav.find(f"{NCX_NS}navLabel/{NCX_NS}text")
        content = nav.find(f"{NCX_NS}content")
        if label is None or content is None:
            continue
        src = content.get("src", "")
        m = _PART_RE.match(src)
        if m is None:
            # Ogni voce del TOC verificata punta a index_split_NNN.html. Se
            # cambia formato non e' piu' terreno verificato: fail-closed.
            raise ValueError(f"voce TOC con href inatteso, non verificato: {src!r}")
        entries.append(TocEntry(title=(label.text or "").strip(), start_num=int(m.group(1))))
    if not entries:
        raise ValueError("toc.ncx senza navPoint: TOC vuoto o formato cambiato")
    return entries


def _max_part_num(zf: zipfile.ZipFile) -> int:
    nums = [int(m.group(1)) for name in zf.namelist() if (m := _PART_RE.match(name))]
    if not nums:
        raise ValueError("nessun file index_split_NNN.html nell'epub")
    return max(nums)


@dataclass
class Block:
    tag: str            # "h1" | "h2" | "h3" | "p"
    text: str
    img_only: bool       # <p> il cui unico contenuto e' un <img> (nessun altro testo)
    fully_italic: bool   # tutto il testo del blocco e' dentro <span class="italic">


class _BlockParser(HTMLParser):
    """Estrae i blocchi top-level (h1/h2/h3/p) dal <body>, tracciando per
    ognuno se e' un <img> nudo e se e' interamente avvolto in italic — le due
    condizioni che, in coppia consecutiva, identificano una didascalia
    Delphi (vedi docstring modulo)."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[Block] = []
        self._in_body = False
        self._tag: str | None = None
        self._text: list[str] = []
        self._has_nonimg = False
        self._has_img = False
        self._italic_depth = 0
        self._has_text_outside_italic = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "body":
            self._in_body = True
            return
        if not self._in_body:
            return
        if tag in ("h1", "h2", "h3", "p"):
            self._tag = tag
            self._text = []
            self._has_nonimg = False
            self._has_img = False
            self._italic_depth = 0
            self._has_text_outside_italic = False
        elif tag == "img":
            if self._tag is not None:
                self._has_img = True
        elif tag == "span":
            if self._tag is not None and dict(attrs).get("class") == "italic":
                self._italic_depth += 1

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "body":
            self._in_body = False
        elif tag == "span" and self._italic_depth > 0:
            self._italic_depth -= 1
        elif tag in ("h1", "h2", "h3", "p") and tag == self._tag:
            text = "".join(self._text).strip()
            img_only = self._has_img and not self._has_nonimg
            fully_italic = bool(text) and not self._has_text_outside_italic
            self.blocks.append(Block(tag, text, img_only, fully_italic))
            self._tag = None

    def handle_data(self, data: str) -> None:
        if self._tag is None:
            return
        if data.strip():
            self._has_nonimg = True
            if self._italic_depth == 0:
                self._has_text_outside_italic = True
        self._text.append(data)


def _page_blocks(zf: zipfile.ZipFile, num: int) -> list[Block]:
    html = zf.read(f"index_split_{num:03d}.html").decode("utf-8")
    parser = _BlockParser()
    parser.feed(html)
    return parser.blocks


def _strip_captions(blocks: list[Block]) -> list[Block]:
    """Rimuove le coppie [img nudo, didascalia interamente italic] e ogni
    <img> nudo residuo (diagrammi decorativi senza didascalia): entrambi non
    contribuiscono mai testo, ma un <img> nudo isolato lascerebbe comunque
    un blocco vuoto nell'elenco.

    Eccezione verificata: sulla pagina-titolo di ogni opera, l'iconcina
    decorativa sotto l'<h1> e' seguita dalla riga "Translated by X" — che e'
    ANCH'ESSA interamente dentro <span class="italic"> (stessa firma HTML
    della didascalia-ritratto). Senza l'eccezione qui sotto, la riga del
    traduttore verrebbe scartata insieme all'icona: mai una didascalia
    reale, va sempre tenuta (poi eventualmente tagliata a parte dal
    confine blurb/corpo in _extract_work, non qui)."""
    out: list[Block] = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b.img_only:
            nxt = blocks[i + 1] if i + 1 < len(blocks) else None
            is_caption = (
                nxt is not None and nxt.fully_italic
                and not _TRANSLATED_BY_RE.match(nxt.text)
            )
            if is_caption:
                i += 2  # scarta immagine + didascalia
                continue
            i += 1  # scarta solo l'immagine nuda
            continue
        out.append(b)
        i += 1
    return out


def _extract_work(zf: zipfile.ZipFile, entry: TocEntry, end_num: int) -> tuple[Work, str | None]:
    """Ritorna (Work, motivo-non-pubblicabile). Il secondo e' None se
    l'estrazione e' riuscita."""
    blocks: list[Block] = []
    for num in range(entry.start_num, end_num + 1):
        blocks.extend(_page_blocks(zf, num))
    blocks = [b for b in blocks if b.tag != "h1"]  # titolo: gia' nell'H1 di common.render
    blocks = _strip_captions(blocks)

    translatore = None
    for b in blocks:
        m = _TRANSLATED_BY_RE.match(b.text)
        if m:
            translatore = m.group(1).strip()
            break

    if entry.title in NO_CONTENTS_MARKER:
        marker = NO_CONTENTS_MARKER[entry.title]
        if marker == "":
            body_blocks = blocks  # nessun blurb: si tiene tutto (incl. "Translated by")
        else:
            idx = next((i for i, b in enumerate(blocks) if b.text == marker), None)
            if idx is None:
                return None, f"marker {marker!r} non trovato (NO_CONTENTS_MARKER)"
            body_blocks = blocks[idx:]
    else:
        idx = next((i for i, b in enumerate(blocks) if b.tag == "h2" and b.text == "CONTENTS"), None)
        if idx is None:
            return None, "nessun <h2>CONTENTS</h2> e non in NO_CONTENTS_MARKER"
        body_blocks = blocks[idx:]

    text = "\n\n".join(b.text for b in body_blocks if b.text)
    if not text.strip():
        return None, "corpo vuoto dopo il taglio"
    return Work(title=entry.title, text=text, kind="work", traduttore=translatore), None


@dataclass
class ExtractResult:
    works: list[Work] = field(default_factory=list)
    toc_titles: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)   # in EXPECTED_WORKS ma non nel TOC
    unmarked: list[str] = field(default_factory=list)   # nel TOC ma non estratta (confine ignoto)


def extract(epub_path: Path) -> ExtractResult:
    expected = set(EXPECTED_WORKS)
    with zipfile.ZipFile(epub_path) as zf:
        entries = _parse_toc(zf)
        last_num = _max_part_num(zf)
        toc_titles = [e.title for e in entries]

        # Vocabolario chiuso su tutte e tre le categorie: una voce del TOC
        # che non e' ne' sezione, ne' apparato, ne' opera attesa e' terreno
        # non verificato — fail-closed piuttosto che instradarla altrove.
        unknown = [
            t for t in toc_titles
            if t not in SECTION_TITLES and t not in APPARATUS_TITLES and t not in expected
        ]
        if unknown:
            raise ValueError(f"voci TOC non classificate (ne' sezione ne' apparato ne' opera attesa): {unknown}")

        found_titles = set(toc_titles)
        missing = [t for t in EXPECTED_WORKS if t not in found_titles]

        works: list[Work] = []
        unmarked: list[str] = []
        for i, entry in enumerate(entries):
            if entry.title not in expected:
                continue
            end_num = entries[i + 1].start_num - 1 if i + 1 < len(entries) else last_num
            work, reason = _extract_work(zf, entry, end_num)
            if work is None:
                unmarked.append(f"{entry.title}: {reason}")
                continue
            works.append(work)

    return ExtractResult(works=works, toc_titles=toc_titles, missing=missing, unmarked=unmarked)
