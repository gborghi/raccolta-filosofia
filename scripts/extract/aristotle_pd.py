# scripts/extract/aristotle_pd.py
"""Sostituisce, DENTRO VaultPhilosophy/Philosophers/Aristotle/_raw/, le opere
che aristotle.py estrae dall'epub Delphi con un traduttore/edizione ANCORA
protetti in UE (regola del progetto: libera dal 1 gennaio di morte-traduttore
+ 71 anni). aristotle.py stesso non lo sa fare: il traduttore Delphi e'
catturato per-opera (Work.traduttore) ma e' comunque quello che l'epub
contiene, non negoziabile lato adapter Delphi. Va chiamato DOPO run_aristotle()
in run.py cosi' sovrascrive i file gia' scritti.

Le 7 opere toccate (vedi ricerca completa in sessione, non ripetuta qui):
  - Metaphysics (980a): Ross (trad. inglese) † 1971, protetto -> sostituito
    con il GRECO originale (nessun traduttore di mezzo), edizione critica
    Ross 1924/Perseus Digital Library (CTS urn:cts:greekLit:tlg0086.tlg025,
    confermato leggendo __cts__.xml: title "Metaphysics"). Il greco antico e'
    PD di per se'; la costituzione critica del testo di Ross e la codifica
    TEI di Perseus sono qui trattate come "gia' libere" per assunzione del
    committente (vedi nota in fondo al modulo) e non riverificate da questo
    codice — Perseus e' comunque citato per esteso in `edizione`.
  - Nicomachean Ethics (1094a): Ross † 1971, protetto -> D. P. Chase † 1902
    (pd_year 1973), Project Gutenberg #8438.
  - Categories (1a): Edghill † 1964, protetto -> Octavius Freire Owen † 1873
    (pd_year 1944), stessa traduzione (Bohn 1853, "The Organon") gia' usata
    da Delphi per "On Interpretation" nello stesso epub -- qui va presa da
    Wikisource perche' Delphi NON la usa per Categories (usa Edghill).
  - Posterior Analytics (71a): Mure † 1979, protetto -> Owen, stesso Organon,
    Wikisource (2 sotto-pagine Book 1 + Book 2).
  - On Length and Shortness of Life (464b), On Youth Old Age... (467b):
    G. R. T. Ross † 1959, protetto (libero solo dal 2030). Nessuna
    alternativa pubblicabile trovata: l'unica versione PD individuata
    (Thomas Taylor, 1808, † Taylor 1835) esiste su archive.org solo come
    scansione di 56 pagine (frontespizio + introduzione, OCR pessimo,
    NON il testo dei trattati) -- inutilizzabile. Cancellati (fail-closed).
  - Economics (1343a): Armstrong, morte non accertabile. L'unica alternativa
    PD individuata (Edward Walford, Bohn's Classical Library 1853,
    archive.org "politicseconomic00arisrich") esiste solo come OCR grezzo
    non corretto (colonne a fronte con note sovrapposte, refusi diffusi:
    "Tur" per "The", note a margine che si infilano a meta' frase...):
    non pubblicabile senza editing manuale, fuori scope. Cancellato.

Wikisource (Categories, Posterior Analytics): le pagine dell'opera NON
contengono il testo -- lo transcludono dal namespace Page: tramite il tag
parser <pages index=... from=... to=.../> (ProofreadPage), risolto solo
a rendering. Per questo si scarica l'HTML GIA' RENDERIZZATO via action=parse
(api.php), non il wikitext grezzo (action=raw), e lo si ripulisce da:
  - <sup class="reference">: richiami di nota numerati
  - <span class="pagenum ...">: marcatori di numero pagina (invisibili)
  - <span class="wst-sidenote ...">: note a margine ANALITICHE di Owen
    (riassunti per paragrafo, non testo di Aristotele -- sono lo stesso
    materiale duplicato nella "Concise Table of Contents"/"Table of
    Contents" a inizio pagina, che e' gia' fuori dal blocco che leggiamo)
  - tutto cio' che segue l'ancora id="Notes" (le note del traduttore, dove
    presenti) o class="licenseContainer" (il banner di licenza PD-old di
    Wikisource): mai testo di Aristotele.
Verificato leggendo l'HTML reale di Categories (nota "Translator's
annotations not included" NON vale li': ha note + licenza) e di Posterior
Analytics Book 1/2 (quella nota vale: nessuna nota, nessuna licenza visibile
-- solo intestazioni <h3>Chapter N</h3> dirette). Il parser sotto gestisce
entrambi i casi senza assumere quale si applichi.
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from .common import slugify
from .sources import RAW_ROOT

CACHE_DIR = Path(RAW_ROOT) / "aristotle_pd"
VAULT_ROOT = Path(__file__).resolve().parents[3] / "VaultPhilosophy"  # fratello di quartz-philosophy/
OUT_DIR = VAULT_ROOT / "Philosophers" / "Aristotle" / "_raw"

USER_AGENT = "Mozilla/5.0 (compatible; SubjectBrainPhilosophy/1.0)"
TEI_NS = "{http://www.tei-c.org/ns/1.0}"


def _ssl_context() -> ssl.SSLContext | None:
    """Il certificato radice di sistema di Python su Windows e' spesso
    obsoleto (verificato in sessione: fallisce con "certificate has expired"
    su host verificati a mano con curl -- che usa il bundle di Git for
    Windows, aggiornato). Se certifi e' installato si usa il suo bundle
    esplicitamente; altrimenti si lascia fare al contesto di default
    (funzionera' se il sistema ha un truststore aggiornato)."""
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


# --------------------------------------------------------------------------
# Scaricamento con cache su disco (RAW_ROOT/aristotle_pd/), mai /tmp: una
# volta scaricato un file non si ritocca piu' la rete per quello, come gli
# altri adapter che leggono blob gia' presenti in RAW_ROOT.
# --------------------------------------------------------------------------

def _fetch(urls: list[str], cache_name: str) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / cache_name
    if path.exists():
        return path.read_text(encoding="utf-8")
    last_err: Exception | None = None
    ctx = _ssl_context()
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
                data = resp.read().decode("utf-8", errors="replace")
            path.write_text(data, encoding="utf-8")
            return data
        except Exception as exc:  # noqa: BLE001 - proviamo il mirror successivo
            last_err = exc
            continue
    raise RuntimeError(f"impossibile scaricare {cache_name!r}: {last_err}")


def _wikisource_html(page_title: str, cache_name: str) -> str:
    encoded = urllib.parse.quote(page_title, safe="/")
    url = (
        "https://en.wikisource.org/w/api.php?action=parse&page="
        f"{encoded}&prop=text&format=json"
    )
    raw = _fetch([url], cache_name)
    data = json.loads(raw)
    if "error" in data:
        raise ValueError(f"Wikisource API error per {page_title!r}: {data['error']}")
    return data["parse"]["text"]["*"]


# --------------------------------------------------------------------------
# Frontmatter: NON riusa common.render()/write_work() perche' li' edizione/
# anno_edizione/pd_year sono fissi per Source (un solo epub condiviso da
# tutte le opere Aristotele); qui invece ogni opera ha fonte, traduttore e
# pd_year completamente diversi -- serve un render parametrizzato per-opera.
# --------------------------------------------------------------------------

def _yaml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _render(*, title: str, lang: str, edizione: str, traduttore: str | None,
            anno_edizione: int | None, pd_year: int, kind: str, text: str) -> str:
    lines = [
        "---",
        f'title: "{_yaml_escape(title)}"',
        'philosopher: "Aristotle"',
        f'lang: "{_yaml_escape(lang)}"',
        f'edizione: "{_yaml_escape(edizione)}"',
        f'traduttore: "{_yaml_escape(traduttore)}"' if traduttore else "traduttore: null",
        f"anno_edizione: {anno_edizione}" if anno_edizione else "anno_edizione: null",
        f"pd_year: {pd_year}",
        'source_key: "aristotle"',
        f'kind: "{_yaml_escape(kind)}"',
        "tomo: null",
        "---",
        "",
        f"# {title}",
        "",
        text.strip(),
        "",
    ]
    return "\n".join(lines)


def _write(*, title: str, **kwargs) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{slugify(title)}.md"
    path.write_text(_render(title=title, **kwargs), encoding="utf-8")
    return path


def _delete(title: str) -> Path:
    path = OUT_DIR / f"{slugify(title)}.md"
    path.unlink(missing_ok=True)
    return path


# --------------------------------------------------------------------------
# Owen / Wikisource ("The Organon", trad. Octavius Freire Owen, 1853,
# † 1873 -> pd_year 1944)
# --------------------------------------------------------------------------

_REF_RE = re.compile(r'<sup\b[^>]*\bclass="[^"]*\breference\b[^"]*"[^>]*>.*?</sup>', re.S)
_PAGENUM_RE = re.compile(r'<span><span class="pagenum[^"]*"[^>]*>.*?</span></span></span>', re.S)
_SIDENOTE_RE = re.compile(r'<span class="wst-sidenote[^"]*"[^>]*>.*?</span></span>', re.S)


class _OwenTextExtractor(HTMLParser):
    """Estrae blocchi di paragrafo dall'HTML gia' ripulito (vedi regex sopra)
    di una pagina Wikisource dell'Organon di Owen. Flush-su-start-tag invece
    di aspettare la chiusura corretta: l'HTML transcluso da ProofreadPage a
    cavallo di pagina a volte non chiude i <p> in modo pulito (verificato su
    Categories, capitolo XV: testo di corpo senza <p> di apertura). Un
    nuovo <p>/<div>/<h1-6> flusha comunque il buffer accumulato fino li',
    quindi il confine di paragrafo resta corretto anche col markup rotto."""

    _FLUSH_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._buf: list[str] = []
        self._skip_tag: str | None = None
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs) -> None:
        if self._skip_tag is not None:
            if tag == self._skip_tag:
                self._skip_depth += 1
            return
        if tag == "style":  # CSS inline: mai testo, altrimenti leaka nel buffer
            self._skip_tag = "style"
            self._skip_depth = 1
            return
        cls = dict(attrs).get("class") or ""
        if tag == "span" and "mw-editsection" in cls:
            # Link "[edit]" accanto a ogni <h3>Chapter N</h3> (MediaWiki):
            # mai testo di Aristotele.
            self._skip_tag = "span"
            self._skip_depth = 1
            return
        if tag in self._FLUSH_TAGS:
            self._flush()

    def handle_startendtag(self, tag, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag) -> None:
        if self._skip_tag is not None and tag == self._skip_tag:
            self._skip_depth -= 1
            if self._skip_depth == 0:
                self._skip_tag = None

    def handle_data(self, data) -> None:
        if self._skip_tag is None:
            self._buf.append(data)

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if text:
            self.blocks.append(text)
        self._buf = []

    def close(self) -> None:
        self._flush()
        super().close()


def _is_boilerplate_caption(block: str) -> bool:
    """Titoli/intestazioni di pagina Wikisource ripetuti (es. "ARISTOTLE'S
    ORGANON." in cima a ogni opera-radice, "THE CATEGORIES." ripetuto):
    sempre TUTTO maiuscolo (a differenza di "Chap. I.—..." o "Chapter 1",
    che hanno lettere minuscole) -- criterio generico, non un elenco fisso
    di stringhe per opera."""
    letters = [c for c in block if c.isalpha()]
    return bool(letters) and block == block.upper()


def _owen_page_text(page_title: str, cache_name: str) -> str:
    html_raw = _wikisource_html(page_title, cache_name)
    start = html_raw.find('<div class="prp-pages-output"')
    if start == -1:
        raise ValueError(
            f'{page_title!r}: nessun <div class="prp-pages-output"> — pagina non transclusa '
            "come atteso, struttura Wikisource cambiata"
        )
    body = html_raw[start:]
    for marker in ('id="Notes"', 'class="licenseContainer"'):
        cut = body.find(marker)
        if cut != -1:
            body = body[:cut]
    body = _REF_RE.sub("", body)
    body = _PAGENUM_RE.sub("", body)
    body = _SIDENOTE_RE.sub("", body)
    parser = _OwenTextExtractor()
    parser.feed(body)
    parser.close()
    blocks = [b for b in parser.blocks if not _is_boilerplate_caption(b)]
    if not blocks:
        raise ValueError(f"{page_title!r}: corpo vuoto dopo la pulizia")
    return "\n\n".join(blocks)


def _fetch_categories() -> str:
    return _owen_page_text("Organon (Owen)/Categories", "owen_categories.html")


def _fetch_posterior_analytics() -> str:
    book1 = _owen_page_text(
        "Organon (Owen)/The Posterior Analytics/Book 1", "owen_pa_book1.html"
    )
    book2 = _owen_page_text(
        "Organon (Owen)/The Posterior Analytics/Book 2", "owen_pa_book2.html"
    )
    return f"BOOK I\n\n{book1}\n\nBOOK II\n\n{book2}"


# --------------------------------------------------------------------------
# D. P. Chase / Project Gutenberg #8438 (Nicomachean Ethics, 1847, † 1902
# -> pd_year 1973)
# --------------------------------------------------------------------------

def _fetch_nicomachean_ethics() -> str:
    raw = _fetch(
        [
            "https://www.gutenberg.org/cache/epub/8438/pg8438.txt",
            "https://mirror.csclub.uwaterloo.ca/gutenberg/8/4/3/8438/8438-0.txt",
        ],
        "gutenberg_8438_nicomachean_ethics.txt",
    )
    start_marker = "ARISTOTLE’S ETHICS"
    # Il marcatore compare due volte: una nel Contents iniziale ("ARISTOTLE'S
    # ETHICS\n\nBOOK I\n\nBOOK II\n...\n\nNOTES", puro indice), una come vera
    # intestazione del corpo (seguita da "BOOK I" poi "Chapter I." e la prosa
    # vera). rindex prende l'ultima occorrenza prima delle NOTES; il controllo
    # "Chapter I." sotto verifica che non sia comunque l'indice.
    try:
        start = raw.rindex(start_marker)
    except ValueError as exc:
        raise ValueError(
            "marcatore di inizio corpo (\"ARISTOTLE'S ETHICS\") non trovato nel testo "
            "Gutenberg #8438: struttura cambiata"
        ) from exc
    end = raw.find("\nNOTES\n", start)
    if end == -1:
        raise ValueError(
            "marcatore di fine corpo (\"NOTES\") non trovato dopo l'inizio: struttura cambiata"
        )
    body = raw[start:end]
    if "Chapter I." not in body[:400]:
        raise ValueError(
            "l'occorrenza di \"ARISTOTLE'S ETHICS\" trovata non e' seguita a breve da "
            "\"Chapter I.\": presa la voce d'indice invece dell'intestazione del corpo, "
            "o struttura cambiata"
        )
    body = body.replace("\r\n", "\n")
    body = re.sub(r"\[\d+\]", "", body)          # richiami di nota inline: "[12]"
    body = re.sub(r"_([^_\n]+)_", r"\1", body)   # corsivo Gutenberg: _parola_ -> parola
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


# --------------------------------------------------------------------------
# Greco / Perseus Digital Library (nessun traduttore: l'originale e' PD di
# per se'; edizione critica Ross 1924, codifica TEI Perseus CC BY-SA)
# --------------------------------------------------------------------------

_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI",
          "XII", "XIII", "XIV", "XV"]


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _tei_text(elem: ET.Element, skip: frozenset[str]) -> str:
    """Testo di un elemento TEI, ricorsivo, che scarta il contenuto degli
    elementi in `skip` (apparato: <del> = lezione espunta dall'editore,
    <bibl> = citazione bibliografica moderna in inglese) ma NE MANTIENE la
    coda (.tail): il testo dopo il tag di chiusura appartiene comunque al
    flusso principale. <add> (supplemento editoriale che l'edizione stampa
    come testo) e <quote>/<l> (versi citati da Aristotele stesso, es. da
    Parmenide/Esiodo) restano dentro il flusso normale."""
    parts = [elem.text or ""]
    for child in elem:
        tag = _local_tag(child.tag)
        if tag in skip:
            pass
        elif tag == "gap":
            parts.append(child.get("rend") or "")
        else:
            parts.append(_tei_text(child, skip))
        parts.append(child.tail or "")
    return "".join(parts)


def _fetch_metaphysics_greek() -> str:
    raw = _fetch(
        [
            "https://raw.githubusercontent.com/PerseusDL/canonical-greekLit/"
            "master/data/tlg0086/tlg025/tlg0086.tlg025.perseus-grc2.xml"
        ],
        "perseus_tlg0086_tlg025_grc2.xml",
    )
    root = ET.fromstring(raw)
    body = root.find(f".//{TEI_NS}body")
    if body is None:
        raise ValueError("Perseus tlg0086.tlg025: <body> assente, struttura TEI cambiata")
    edition = body.find(f'{TEI_NS}div[@type="edition"]')
    if edition is None:
        raise ValueError('Perseus tlg0086.tlg025: <div type="edition"> assente')

    skip = frozenset({"del", "bibl", "note", "app"})
    book_divs = edition.findall(f'{TEI_NS}div[@type="textpart"][@subtype="book"]')
    if len(book_divs) < 14:
        raise ValueError(
            f"Perseus tlg0086.tlg025: attesi 14 libri, trovati {len(book_divs)} "
            "(vedi __cts__.xml) — struttura cambiata"
        )

    books_out: list[str] = []
    for i, book in enumerate(book_divs):
        label = _ROMAN[i] if i < len(_ROMAN) else str(i + 1)
        section_divs = book.findall(f'{TEI_NS}div[@type="textpart"][@subtype="section"]')
        paras: list[str] = []
        for section in section_divs:
            for p in section.findall(f"{TEI_NS}p"):
                text = re.sub(r"\s+", " ", _tei_text(p, skip)).strip()
                if text:
                    paras.append(text)
        if not paras:
            raise ValueError(f"Perseus tlg0086.tlg025: libro {label} senza paragrafi")
        books_out.append(f"BOOK {label}\n\n" + "\n\n".join(paras))
    return "\n\n".join(books_out)


# --------------------------------------------------------------------------
# Orchestrazione
# --------------------------------------------------------------------------

def run_aristotle_pd() -> list[str]:
    """Sovrascrive le opere protette e cancella le 3 irrisolte. Da chiamare
    DOPO run_aristotle(): fail-closed, propaga qualunque eccezione (una
    fonte esterna cambiata silenziosamente non deve produrre un file
    dimezzato)."""
    log: list[str] = []

    path = _write(
        title="Metaphysics (980a)", lang="grc",
        edizione="Perseus Digital Library, canonical-greekLit tlg0086.tlg025 "
                 "(testo critico W. D. Ross, Oxford 1924; codifica TEI Perseus, CC BY-SA)",
        traduttore=None, anno_edizione=1924, pd_year=1900, kind="work",
        text=_fetch_metaphysics_greek(),
    )
    log.append(f"sostituita: Metaphysics (980a) -> greco, Perseus tlg0086.tlg025 ({path})")

    path = _write(
        title="Nicomachean Ethics (1094a)", lang="en",
        edizione="Project Gutenberg #8438 (D. P. Chase translation, 1847)",
        traduttore="D. P. Chase", anno_edizione=1847, pd_year=1973, kind="work",
        text=_fetch_nicomachean_ethics(),
    )
    log.append(f"sostituita: Nicomachean Ethics (1094a) -> D. P. Chase, Gutenberg #8438 ({path})")

    path = _write(
        title="Categories (1a)", lang="en",
        edizione='Wikisource, "The Organon" (Octavius Freire Owen translation, '
                 "London: Henry G. Bohn, 1853)",
        traduttore="Octavius Freire Owen", anno_edizione=1853, pd_year=1944, kind="work",
        text=_fetch_categories(),
    )
    log.append(f"sostituita: Categories (1a) -> Owen, Wikisource Organon ({path})")

    path = _write(
        title="Posterior Analytics (71a)", lang="en",
        edizione='Wikisource, "The Organon" (Octavius Freire Owen translation, '
                 "London: Henry G. Bohn, 1853)",
        traduttore="Octavius Freire Owen", anno_edizione=1853, pd_year=1944, kind="work",
        text=_fetch_posterior_analytics(),
    )
    log.append(f"sostituita: Posterior Analytics (71a) -> Owen, Wikisource Organon ({path})")

    for title in (
        "On Length and Shortness of Life (464b)",
        "On Youth, Old Age, Life and Death, and Respiration (467b)",
        "Economics (1343a)",
    ):
        path = _delete(title)
        log.append(f"cancellata (nessuna fonte PD pubblicabile trovata): {title} ({path})")

    return log
