# scripts/extract/seneca_pd.py
"""Sostituisce le 2 opere di Seneca il cui traduttore Delphi NON e' PD, con
fonti alternative genuinamente di pubblico dominio. Le altre 24 opere di
Seneca (Aubrey Stewart † 1918, Frank Justus Miller † 1938) restano intatte:
questo script NON le tocca, sovrascrive solo i due file sotto.

1. THE_MORAL_EPISTLES.md — Delphi usa Richard Mott Gummere († 1969, libera
   solo nel 2040). Non esiste un inglese PD utilizzabile (Morell 1786 e'
   solo scansione OCR). Sostituito col LATINO ORIGINALE (Seneca stesso,
   morto 65 d.C.: nessun copyright possibile), da The Latin Library —
   testo nudo, zero apparato critico, zero traduzione.

2. ON_THE_SHORTNESS_OF_LIFE.md — Delphi usa John W. Basore († 1958, libera
   nel 2029). Sostituito con l'inglese di Aubrey Stewart († 1918, PD),
   lo stesso traduttore gia' usato per gli altri 10 dialoghi di Seneca in
   questo corpus, preso da Standard Ebooks (edizione proof-read, PD).

Chiamato da run.py DOPO run_source() per Seneca: sovrascrive i due file che
l'estrazione Delphi ha appena scritto con traduttori non-PD.

Rete: una richiesta per pagina, mai in loop aggressivo. Ogni pagina scaricata
viene cachata sotto RAW_ROOT/seneca_pd/ (rifacibile, non un file temporaneo)
e riletta da li' nelle run successive senza richiedere di nuovo la rete.
"""
from __future__ import annotations

import re
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from .common import Work, render
from .sources import RAW_ROOT, Source

USER_AGENT = (
    "Mozilla/5.0 (compatible; SubjectBrain-Philosophy/1.0; "
    "+educational public-domain text mirror; one request per page)"
)
_REQUEST_DELAY_S = 1.0  # cortesia verso i siti: mai a raffica

CACHE_ROOT = Path(RAW_ROOT) / "seneca_pd"
LATIN_LIBRARY_CACHE = CACHE_ROOT / "latin_library"
STANDARD_EBOOKS_CACHE = CACHE_ROOT / "standard_ebooks"


def _ssl_context() -> ssl.SSLContext:
    """Il truststore di default di questa macchina risulta con una CA scaduta
    per alcuni siti Let's Encrypt (verificato: il certificato foglia di
    thelatinlibrary.com e standardebooks.org e' valido, e' la catena di
    default del sistema ad avere un intermedio/radice datato). `certifi`,
    se installato (e' gia' presente come dipendenza transitiva in questo
    ambiente), fornisce un bundle CA aggiornato e risolve senza disabilitare
    la verifica: usato qui in modo opzionale (try/except), il resto della
    pipeline resta pure-stdlib se certifi non c'e'."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _fetch(url: str, cache_path: Path) -> bytes:
    """Scarica (o rilegge dalla cache) i byte grezzi di `url`. Un file gia'
    presente in cache NON viene ri-scaricato: il download e' rifacibile ma
    non ripetuto ad ogni run. Solo le richieste di rete vere aspettano
    _REQUEST_DELAY_S dopo di se', per non martellare il sito."""
    if cache_path.exists():
        return cache_path.read_bytes()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as resp:
            data = resp.read()
    except ssl.SSLCertVerificationError as exc:
        raise ssl.SSLCertVerificationError(
            f"verifica certificato fallita per {url}: {exc}. "
            "Prova 'pip install -U certifi' (bundle CA aggiornato) oppure "
            "verifica l'orologio/truststore di sistema. Non disabilito la "
            "verifica del certificato silenziosamente."
        ) from exc
    cache_path.write_bytes(data)
    time.sleep(_REQUEST_DELAY_S)
    return data


# ---------------------------------------------------------------------------
# 1. THE MORAL EPISTLES -> Epistulae Morales ad Lucilium, latino, The Latin
#    Library.
# ---------------------------------------------------------------------------

_LATIN_LIBRARY_INDEX = "https://www.thelatinlibrary.com/sen.html"
_LATIN_LIBRARY_PAGE = "https://www.thelatinlibrary.com/sen/seneca.{}.shtml"

# Elenco verificato scaricando e leggendo sen.html il {data}: 16 pagine, NON
# la sequenza "seneca.ep2-10.shtml" ipotizzata inizialmente -- l'indice reale
# ha una pagina per libro da I a X, poi pagine multi-libro per XI in poi.
_EPISTLE_PAGE_SLUGS = [
    "ep1", "ep2", "ep3", "ep4", "ep5", "ep6", "ep7", "ep8", "ep9", "ep10",
    "ep11-13", "ep14-15", "ep16", "ep17-18", "ep19", "ep20",
]

_INDEX_HREF_RE = re.compile(r'href="(sen/seneca\.ep[\w-]+\.shtml)"', re.IGNORECASE)
_BORDER_RE = re.compile(r"<p\s+class=border>", re.IGNORECASE)
# "SENECA LVCILIO SVO SALVTEM" (V al posto di U) compare a partire dal libro
# IX: la classe [VU] copre entrambe le grafie senza bisogno di due regex.
_LETTER_HEADER_RE = re.compile(
    r"([IVXLCDM]+)\.?\s*SENECA\s+L[VU]CILIO\s+S[VU]O\s+SAL[VU]TEM\.?",
    re.IGNORECASE,
)

_ROMAN_TABLE = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
    (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(s: str) -> int:
    s = s.upper()
    total, prev = 0, 0
    for ch in reversed(s):
        v = _ROMAN_VALUES[ch]
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total


def _int_to_roman(n: int) -> str:
    out = []
    for v, sym in _ROMAN_TABLE:
        while n >= v:
            out.append(sym)
            n -= v
    return "".join(out)


class _BlockTextExtractor(HTMLParser):
    """Estrae testo nudo, un '\n' per ogni tag di blocco. Niente gestione
    speciale di link o tabelle: lo slice passato in input (vedi
    `_epistle_page_body`) ha gia' escluso pagehead e footer di navigazione,
    quindi qui dentro c'e' solo prosa di Seneca."""

    _BLOCK = {"p", "br", "div"}

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._BLOCK:
            self._chunks.append("\n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"[ \t]*\n[ \t]*", "\n", raw)
        raw = re.sub(r"\n{2,}", "\n\n", raw)
        return raw.strip()


def _verify_epistle_page_list() -> None:
    """Fail-closed: se l'indice del sito e' cambiato rispetto all'elenco
    verificato a mano, meglio fermarsi che pubblicare pagine sbagliate o
    mancanti."""
    index_bytes = _fetch(_LATIN_LIBRARY_INDEX, LATIN_LIBRARY_CACHE / "sen_index.html")
    index_html = index_bytes.decode("latin-1")
    hrefs = _INDEX_HREF_RE.findall(index_html)
    found_slugs = [h.split("seneca.", 1)[1].rsplit(".shtml", 1)[0] for h in hrefs]
    if found_slugs != _EPISTLE_PAGE_SLUGS:
        raise ValueError(
            "elenco pagine Epistulae su thelatinlibrary.com/sen.html e' "
            f"cambiato: atteso {_EPISTLE_PAGE_SLUGS}, trovato {found_slugs}"
        )


def _epistle_page_body(html: str) -> str:
    """Isola il corpo delle lettere. Ogni pagina ha ESATTAMENTE due
    `<p class=border>`: il primo chiude il pagehead editoriale ("L. ANNAEI
    SENECAE / EPISTULARUM ... LIBER N", apparato di impaginazione, non testo
    di Seneca), il secondo apre il footer di navigazione del sito (link ad
    altre pagine: apparato del sito). Verificato su tutte le 16 pagine prima
    di scrivere questo codice -- se una pagina ne avesse un numero diverso,
    e' un segnale che la struttura e' cambiata: fail-closed."""
    matches = list(_BORDER_RE.finditer(html))
    if len(matches) != 2:
        raise ValueError(
            f"attese 2 occorrenze di 'class=border', trovate {len(matches)}: "
            "struttura pagina Latin Library cambiata, non estraggo alla cieca"
        )
    return html[matches[0].start(): matches[1].start()]


def _extract_epistle_page_text(raw_bytes: bytes) -> str:
    # latin-1: il testo latino e' ASCII puro; le uniche eccezioni sono un
    # pugno di citazioni greche rese dal sito con un font Symbol non-Unicode
    # (bytes > 0x7F isolati, es. 'beb\x92\x99tai' per "βεβίωται" in Ep. XII).
    # latin-1 decodifica senza errori e senza perdere/mischiare byte; non
    # tento di indovinare il glifo greco corretto, a differenza del caso
    # gestito in nietzsche.py dove la mappa immagine->carattere era nota.
    html = raw_bytes.decode("latin-1")
    body_html = _epistle_page_body(html)
    parser = _BlockTextExtractor()
    parser.feed(body_html)
    return parser.text()


def _repair_missing_headers(pages_text: list[str]) -> tuple[str, list[tuple[int, str]]]:
    """thelatinlibrary.com/sen/seneca.ep3.shtml omette l'intestazione
    "XXII. SENECA LUCILIO SUO SALUTEM": la pagina passa direttamente dal
    "Vale." della lettera XXI al corpo della lettera XXII senza etichetta
    (verificato a mano: il contenuto non etichettato inizia con "Iam
    intellegis educendum esse te ex istis occupationibus speciosis et
    malis" -- l'incipit noto dell'Epistola 22, che cita la lettera di
    Epicuro a Idomeneo sul ritiro dagli affari pubblici -- e finisce con
    l'unico "Vale." prima dell'header "XXIII." Non e' testo mancante, solo
    l'etichetta numerica).

    Qui il buco viene richiuso RIPRISTINANDO l'intestazione nella sua
    posizione strutturale (subito dopo la fine dell'ultima lettera vista,
    o inizio pagina se e' la prima lettera della pagina) -- non e' testo
    inventato, e' la stessa formula "N. SENECA LUCILIO SUO SALUTEM" usata
    da tutte le altre 123 lettere, con N dedotto dalla sequenza (XXI prima,
    XXIII dopo). Se il buco fosse piu' di una lettera, o in una posizione
    diversa da quella qui verificata, si ferma: non indovina."""
    expected = 1
    repairs: list[tuple[int, str]] = []
    out_pages: list[str] = []
    for page_slug, text in zip(_EPISTLE_PAGE_SLUGS, pages_text):
        matches = list(_LETTER_HEADER_RE.finditer(text))
        offset_shift = 0
        prev_end = 0
        working = text
        for m in matches:
            numeral_val = _roman_to_int(m.group(1))
            if numeral_val != expected:
                if numeral_val != expected + 1:
                    raise ValueError(
                        f"buco di piu' di una lettera tra {expected} e "
                        f"{numeral_val} in pagina {page_slug}: non riparo alla "
                        "cieca, fail-closed"
                    )
                insert_pos = prev_end + offset_shift
                heading = f"{_int_to_roman(expected)}. SENECA LUCILIO SUO SALUTEM"
                working = working[:insert_pos] + heading + "\n\n" + working[insert_pos:]
                offset_shift += len(heading) + 2
                repairs.append((expected, page_slug))
                expected += 1
            expected = numeral_val + 1
            prev_end = m.end()
        out_pages.append(working)
    return "\n\n".join(out_pages), repairs


@dataclass
class EpistulaeResult:
    text: str
    letter_count: int
    repairs: list[tuple[int, str]] = field(default_factory=list)


def _normalize_headers(text: str) -> str:
    """thelatinlibrary.com non e' internamente coerente sulla punteggiatura
    delle intestazioni: 123 lettere su 124 usano "N. SENECA LUCILIO SUO
    SALUTEM", ma la lettera XXI sulla pagina e' scritta "XXI SENECA LUCILIO
    SUO SALUTEM" (punto mancante) -- verificato a mano. Senza il punto lo
    heading-detector a valle (scripts/atomize/headings.py, regex
    `^[IVXLCDM]{1,7}\\.`) non riconosce il confine e la lettera XXI finirebbe
    incollata alla coda della XX. Qui si riscrive OGNI intestazione trovata
    (numero romano gia' presente nel testo, mai inventato) nella stessa
    forma canonica con punto, uniformando anche l'ortografia V/U (mero
    fatto tipografico: il latino classico non distingueva le due lettere,
    "LVCILIO" e "LUCILIO" sono la stessa parola) usata gia' dai libri I-VIII
    del sito stesso."""
    def _canonical(m: re.Match) -> str:
        return f"{m.group(1).upper()}. SENECA LUCILIO SUO SALUTEM"
    return _LETTER_HEADER_RE.sub(_canonical, text)


def build_epistulae_morales() -> EpistulaeResult:
    _verify_epistle_page_list()
    pages_text = []
    for slug in _EPISTLE_PAGE_SLUGS:
        url = _LATIN_LIBRARY_PAGE.format(slug)
        cache_path = LATIN_LIBRARY_CACHE / f"seneca.{slug}.shtml"
        raw = _fetch(url, cache_path)
        pages_text.append(_extract_epistle_page_text(raw))
    full_text, repairs = _repair_missing_headers(pages_text)
    full_text = _normalize_headers(full_text)
    letter_count = len(_LETTER_HEADER_RE.findall(full_text))
    if letter_count != 124:
        # Fail-closed: le Epistulae Morales ad Lucilium sono 124 per
        # tradizione manoscritta. Un conteggio diverso significa che
        # qualcosa e' cambiato (pagina persa, riparazione sbagliata,
        # struttura del sito diversa) e non va pubblicato silenziosamente.
        raise ValueError(
            f"attese 124 lettere, raccolte {letter_count}: non pubblico, "
            "verificare a mano prima di procedere"
        )
    return EpistulaeResult(text=full_text, letter_count=letter_count, repairs=repairs)


# ---------------------------------------------------------------------------
# 2. ON THE SHORTNESS OF LIFE -> stesso testo inglese, ma traduzione di
#    Aubrey Stewart (PD) invece di John W. Basore, presa da Standard Ebooks.
# ---------------------------------------------------------------------------

_SE_TEXT_URL = (
    "https://standardebooks.org/ebooks/seneca/dialogues/aubrey-stewart/"
    "text/on-the-shortness-of-life"
)
_SE_COLOPHON_URL = (
    "https://standardebooks.org/ebooks/seneca/dialogues/aubrey-stewart/"
    "text/colophon"
)
_SE_TRANSLATOR_RE = re.compile(
    r'<b epub:type="z3998:personal-name">([^<]+)</b>'
)
_SE_EDITION_YEAR_RE = re.compile(r'<time datetime="(\d{4})-\d{2}-\d{2}')
_SE_TITLE_RE = re.compile(r'<h2 epub:type="title">([^<]+)</h2>')


class _StandardEbooksTextExtractor(HTMLParser):
    """Estrae il testo dentro <main>, scartando i marcatori di nota a piè
    di pagina (<a epub:type="noteref">73</a>): sono apparato del
    traduttore/editor (rimandi a endnotes.xhtml, non incluso), non prosa di
    Seneca. Il resto di <main> e' solo titolo, dedica ("To Paulinus.") e
    capitoli numerati: nessun altro apparato da filtrare, il footer di
    navigazione ("Previous"/"Next") sta fuori da <main>."""

    _BLOCK = {"p", "h2", "h3", "header", "section"}

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._in_main = False
        self._skip_depth = 0
        self._in_h3 = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_d = dict(attrs)
        if tag == "main":
            self._in_main = True
            return
        if not self._in_main:
            return
        if tag == "a" and attrs_d.get("epub:type") == "noteref":
            self._skip_depth += 1
            return
        if tag in self._BLOCK:
            self._chunks.append("\n")
        if tag == "h3":
            self._in_h3 = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "main":
            self._in_main = False
            return
        if self._in_main and tag == "a" and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "h3" and self._in_h3:
            # scripts/atomize/headings.py riconosce le intestazioni capitolo
            # solo nella forma "I." (numero romano + punto): l'<h3> di
            # Standard Ebooks contiene solo "I" nudo. Il punto va aggiunto
            # qui, dove sappiamo con certezza strutturale che questo testo
            # e' un numero di capitolo (non e' testo inventato: e' la stessa
            # numerazione "I, II, III..." gia' presente nell'<h3>, solo
            # riformattata per essere riconosciuta a valle -- Delphi/Basore
            # scriveva gli stessi numeri con lo stesso punto).
            self._chunks.append(".")
            self._in_h3 = False

    def handle_data(self, data: str) -> None:
        if self._in_main and self._skip_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"[ \t]*\n[ \t]*", "\n", raw)
        raw = re.sub(r"\n{2,}", "\n\n", raw)
        return raw.strip()


@dataclass
class ShortnessOfLifeResult:
    text: str
    translator: str
    anno_edizione: int


def build_on_the_shortness_of_life() -> ShortnessOfLifeResult:
    text_raw = _fetch(_SE_TEXT_URL, STANDARD_EBOOKS_CACHE / "on-the-shortness-of-life.html")
    colophon_raw = _fetch(_SE_COLOPHON_URL, STANDARD_EBOOKS_CACHE / "colophon.html")
    text_html = text_raw.decode("utf-8")
    colophon_html = colophon_raw.decode("utf-8")

    title_m = _SE_TITLE_RE.search(text_html)
    if title_m is None or title_m.group(1).strip() != "On the Shortness of Life":
        raise ValueError(
            f"titolo inatteso sulla pagina Standard Ebooks: {title_m.group(1) if title_m else None!r}"
        )

    translator_m = _SE_TRANSLATOR_RE.search(colophon_html)
    if translator_m is None or translator_m.group(1).strip() != "Aubrey Stewart":
        raise ValueError(
            f"traduttore nel colophon Standard Ebooks non e' Aubrey Stewart: "
            f"{translator_m.group(1) if translator_m else None!r}"
        )

    year_m = _SE_EDITION_YEAR_RE.search(colophon_html)
    if year_m is None:
        raise ValueError("anno di prima edizione non trovato nel colophon Standard Ebooks")
    anno_edizione = int(year_m.group(1))

    parser = _StandardEbooksTextExtractor()
    parser.feed(text_html)
    body_text = parser.text()
    if not body_text.startswith("On the Shortness of Life"):
        raise ValueError("corpo estratto non inizia col titolo atteso, apparato non isolato correttamente")

    return ShortnessOfLifeResult(
        text=body_text, translator=translator_m.group(1).strip(), anno_edizione=anno_edizione
    )


# ---------------------------------------------------------------------------
# Scrittura file e report
# ---------------------------------------------------------------------------

SENECA_SOURCE_KEY = "seneca"
SENECA_NAME = "Seneca"
VAULT_ROOT = Path(__file__).resolve().parents[3] / "VaultPhilosophy"  # fratello di quartz-philosophy/
OUT_DIR = VAULT_ROOT / "Philosophers" / SENECA_NAME / "_raw"


def _write_fixed(work: Work, source: Source, filename: str) -> Path:
    """Come common.write_work(), ma con nome file ESPLICITO invece che
    derivato da slugify(work.title). Serve per THE_MORAL_EPISTLES.md: il
    titolo cambia da inglese a latino ("Epistulae Morales ad Lucilium"),
    ma il file deve SOVRASCRIVERE quello Delphi esistente con lo stesso
    nome, non crearne uno nuovo affiancato al vecchio."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / filename
    path.write_text(render(work, source), encoding="utf-8")
    return path


def run_seneca_pd() -> list[str]:
    """Sovrascrive le due opere protette. Da chiamare DOPO run_source() per
    Seneca (stesso pattern di run_aristotle_pd() in aristotle_pd.py):
    fail-closed, propaga qualunque eccezione invece di pubblicare a meta'."""
    log: list[str] = []

    epistulae = build_epistulae_morales()
    latin_source = Source(
        key=SENECA_SOURCE_KEY, name=SENECA_NAME, adapter="seneca_pd", lang="la",
        edizione="The Latin Library", traduttore=None, anno_edizione=None, pd_year=1900,
    )
    epistulae_work = Work(
        title="Epistulae Morales ad Lucilium", text=epistulae.text, kind="work", traduttore=None,
    )
    path = _write_fixed(epistulae_work, latin_source, "THE_MORAL_EPISTLES.md")
    log.append(
        f"sostituita: THE MORAL EPISTLES -> latino originale, The Latin Library, "
        f"{epistulae.letter_count} lettere ({path})"
    )
    for numeral, page in epistulae.repairs:
        log.append(
            f"  riparata intestazione mancante nella fonte: lettera {numeral} "
            f"(pagina {page}, contenuto presente, solo l'etichetta numerica mancava)"
        )

    shortness = build_on_the_shortness_of_life()
    stewart_source = Source(
        key=SENECA_SOURCE_KEY, name=SENECA_NAME, adapter="seneca_pd", lang="en",
        edizione="Standard Ebooks", traduttore=shortness.translator,
        anno_edizione=shortness.anno_edizione, pd_year=1900,
    )
    shortness_work = Work(
        title="ON THE SHORTNESS OF LIFE", text=shortness.text, kind="work",
        traduttore=shortness.translator,
    )
    path = _write_fixed(shortness_work, stewart_source, "ON_THE_SHORTNESS_OF_LIFE.md")
    log.append(
        f"sostituita: ON THE SHORTNESS OF LIFE -> {shortness.translator}, Standard Ebooks "
        f"{shortness.anno_edizione} ({path})"
    )

    return log
