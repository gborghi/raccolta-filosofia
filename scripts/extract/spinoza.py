# scripts/extract/spinoza.py
"""Adapter bespoke per Baruch Spinoza. Fonte: 'Collected Works of Baruch
Spinoza', Delphi Classics, epub (Ops/, file NNN.html sequenziali).

PROVENIENZA (verificata leggendo l'epub):
- editore Delphi Classics (stesso modello PD degli altri Delphi del progetto:
  traduzioni ottocentesche di pubblico dominio). Traduzione principale di
  R. H. M. Elwes (1883-84, "Translated by R. H. M. Elwes" nelle testate di
  Emendation/TTP/Ethics/Political Treatise/Letters) — PD. Il Breve Trattato usa
  la traduzione di A. Wolf (1910, pre-1928, PD). NON e' la Curley (Princeton
  1985) ne' la Shirley: entrambe protette e ASSENTI da questa edizione.
- Spinoza † 1677: nessun copyright possibile sull'originale. pd_year=1900 (come
  gli altri _delphi): gia' PD.

STRUTTURA (dal toc.ncx, navPoint di primo livello):
  6 OPERE pubblicabili, in quest'ordine di file d'inizio:
    Short Treatise on God, Man and His Well-Being   012  (solo EN: Wolf)
    Treatise on the Emendation of the Intellect     062  (EN 062-085, LA 086-101)
    Theological-Political Treatise                  102  (EN 102-128, LA 129-150)
    Ethics                                          151  (EN 151-182, LA 183-188)
    Political Treatise                              189  (EN 189-206, LA 207-219)
    Selected Letters                                220  (solo EN)
  Ogni opera latina e' introdotta, DENTRO il range dell'opera, da un file
  "The Original Latin Text": li' finisce l'inglese e comincia il latino, che
  questo adapter tiene SEPARATO (rappresentazione `la`, per i file gemelli
  .la.md degli atomi, come le traduzioni .it.md/.en.md del progetto).

  APPARATO scartato: Title page (001), COPYRIGHT (005), The Books (007), e
  tutto da 'The Criticism' (295) in poi — saggi critici su Spinoza (Hegel,
  Schopenhauer, Nietzsche, Marx, Voltaire, Froude, Adler, White), biografie
  e catalogo Delphi: sono SU Spinoza, non DI Spinoza.

Le pagine di sola navigazione interne (CONTENTS, "Translation by ...") si
saltano per titolo/intestazione, come nell'adapter augustine.py.
"""
from __future__ import annotations

import glob
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

# Stessa estrazione a paragrafi puliti dell'adapter NPNF: <body> -> paragrafi
# de-wrappati, sottoalbero <a> (note/rimandi) scartato, parentesi orfane pulite.
from .augustine import _Extractor, _clean
from .common import Work
from .sources import RAW_ROOT, Source

SPINOZA_EPUB_DIR = os.environ.get(
    "SPINOZA_EPUB_DIR",
    "/Users/g.borghi/Library/CloudStorage/Dropbox/remotedir/libri/"
    "libri_svago/Saggi/filosofia/spinoza",
)

# Opere attese (asserzione fail-closed, come cartesio/aristotle/plato). L'ordine
# e' quello dei file d'inizio nello spine.
EXPECTED_WORKS = [
    "Short Treatise on God, Man and His Well-Being",
    "Treatise on the Emendation of the Intellect",
    "Theological-Political Treatise",
    "Ethics",
    "Political Treatise",
    "Selected Letters",
]

# navPoint di primo livello che aprono l'apparato: da qui in poi (incluso) si
# scarta tutto. 'The Criticism' apre i saggi critici; prima ci sono le 6 opere.
_APPARATUS_FROM = "the criticism"
# navPoint d'apparato in testa, prima delle opere.
_APPARATUS_HEAD = ("title page", "copyright", "the books")

# Confine EN|LA dentro un'opera: il file la cui testata annuncia il latino.
_LATIN_MARKER = re.compile(r"original latin text", re.I)
# Pagine di navigazione interne da saltare.
_SKIP_TITLE = re.compile(r"^(contents|translation by)\b", re.I)

# Ogni opera Delphi si apre con una SINOSSI editoriale (riassunto in terza
# persona scritto da Delphi: "Spinoza's magnum opus, Ethics was written...")
# seguita dal frontespizio e dalla nota del traduttore. Il testo VERO di
# Spinoza comincia alla prima testata STRUTTURALE. Tutto cio' che sta prima
# e' apparato Delphi e si scarta cominciando a raccogliere da qui.
_CONTENT_HEAD = re.compile(
    r"^\s*(PART\b|PARS\b|PREFACE\b|PRAEFATIO\b|PROLOGUS\b|CHAPTER\b|CAPUT\b|"
    r"LETTER\b|EPISTLE\b|BOOK\b|APPENDIX\b|INTRODUCTION\b|NOTICE\b|"
    r"FIRST PART\b|SECOND PART\b|TRACTATUS\b|DEFINITION|AXIOM)",
    re.I,
)


@dataclass
class SpinozaWork:
    title: str
    en_text: str
    la_text: str | None  # None se l'opera non ha originale latino in edizione


@dataclass
class ExtractResult:
    works: list[SpinozaWork]
    toc_titles: list[str] = field(default_factory=list)


def find_epub(source: Source) -> Path:
    for d in (SPINOZA_EPUB_DIR, os.path.join(RAW_ROOT, "spinoza"), RAW_ROOT):
        cands = sorted(glob.glob(os.path.join(d, "*.epub")))
        spz = [c for c in cands if "spinoza" in os.path.basename(c).lower()]
        if spz:
            return Path(spz[0])
    raise FileNotFoundError(f"epub Spinoza (Delphi) non trovato in {SPINOZA_EPUB_DIR}")


def _opf_dir_and_spine(zf: zipfile.ZipFile) -> tuple[str, list[str]]:
    container = zf.read("META-INF/container.xml").decode("utf-8")
    opf_path = re.search(r'full-path="([^"]+)"', container).group(1)
    opf_dir = os.path.dirname(opf_path)
    opf = zf.read(opf_path).decode("utf-8")
    manifest = dict(re.findall(r'<item[^>]*id="([^"]+)"[^>]*href="([^"]+)"', opf))
    if not manifest:
        manifest = dict(
            (re.search(r'id="([^"]+)"', it).group(1),
             re.search(r'href="([^"]+)"', it).group(1))
            for it in re.findall(r"<item\b[^>]*>", opf)
            if 'id="' in it and 'href="' in it
        )
    ids = re.findall(r'<itemref[^>]*idref="([^"]+)"', opf)
    return opf_dir, [manifest[i] for i in ids if i in manifest]


@dataclass
class _Nav:
    title: str
    href: str


def _read_ncx_toplevel(zf: zipfile.ZipFile) -> list[_Nav]:
    ncx_name = next(n for n in zf.namelist() if n.lower().endswith(".ncx"))
    root = ET.fromstring(zf.read(ncx_name).decode("utf-8"))
    ns = {"n": "http://www.daisy.org/z3986/2005/ncx/"}
    navs = []
    for np in root.find("n:navMap", ns).findall("n:navPoint", ns):
        label = (np.find("n:navLabel/n:text", ns).text or "").strip()
        href = np.find("n:content", ns).get("src", "").split("#", 1)[0]
        navs.append(_Nav(re.sub(r"\s+", " ", label), href))
    return navs


def _join(opf_dir: str, href: str) -> str:
    return f"{opf_dir}/{href}" if opf_dir else href


def _title_of(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _first_heading(html: str) -> str:
    m = re.search(r"<h[1-6][^>]*>(.*?)</h[1-6]>", html, re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", m.group(1))).strip() if m else ""


def _paras_of(zf, opf_dir, href) -> list[str]:
    html = zf.read(_join(opf_dir, href)).decode("utf-8", "replace")
    ex = _Extractor()
    ex.feed(html)
    return [c for c in (_clean(p) for p in ex.paragraphs()) if c]


def extract(epub_path: Path) -> ExtractResult:
    with zipfile.ZipFile(epub_path) as zf:
        opf_dir, spine = _opf_dir_and_spine(zf)
        pos = {href: k for k, href in enumerate(spine)}
        navs = _read_ncx_toplevel(zf)

        # confine dell'apparato di coda: primo navPoint 'The Criticism'.
        app_idx = len(spine)
        for n in navs:
            if n.title.lower().startswith(_APPARATUS_FROM) and n.href in pos:
                app_idx = pos[n.href]
                break

        # navPoint delle opere: quelli attesi, non d'apparato, prima di app_idx.
        work_navs = [
            n for n in navs
            if n.title in EXPECTED_WORKS and n.href in pos and pos[n.href] < app_idx
        ]
        found = [n.title for n in work_navs]
        if found != EXPECTED_WORKS:
            raise ValueError(
                f"opere Spinoza inattese: trovate {found}, attese {EXPECTED_WORKS}"
            )

        starts = [pos[n.href] for n in work_navs]
        bounds = starts[1:] + [app_idx]

        works: list[SpinozaWork] = []
        for n, lo, hi in zip(work_navs, starts, bounds):
            # trova il confine EN|LA: primo file nel range la cui testata annuncia
            # il testo latino originale.
            latin_at = None
            for k in range(lo, hi):
                html = zf.read(_join(opf_dir, spine[k])).decode("utf-8", "replace")
                if _LATIN_MARKER.search(_title_of(html)) or _LATIN_MARKER.search(_first_heading(html)):
                    latin_at = k
                    break
            en_hi = latin_at if latin_at is not None else hi

            def content_start(a: int, b: int) -> int:
                """Primo file del range con testata strutturale: prima c'e' solo
                la sinossi/frontespizio Delphi. Fail-safe: se non trova nulla
                (struttura inattesa) torna `a`, senza perdere l'opera."""
                for k in range(a, b):
                    html = zf.read(_join(opf_dir, spine[k])).decode("utf-8", "replace")
                    if _CONTENT_HEAD.match(_first_heading(html)):
                        return k
                return a

            def gather(a: int, b: int) -> str:
                out: list[str] = []
                for k in range(content_start(a, b), b):
                    html = zf.read(_join(opf_dir, spine[k])).decode("utf-8", "replace")
                    t, h = _title_of(html), _first_heading(html)
                    if _SKIP_TITLE.match(t) or _SKIP_TITLE.match(h) or _LATIN_MARKER.search(h):
                        continue
                    out.extend(_paras_of(zf, opf_dir, spine[k]))
                return "\n\n".join(out)

            en_text = gather(lo, en_hi)
            la_text = gather(latin_at, hi) if latin_at is not None else None
            if not en_text.strip():
                raise ValueError(f"opera EN vuota: {n.title!r}")
            if latin_at is not None and not (la_text or "").strip():
                raise ValueError(f"testo latino vuoto per {n.title!r}")
            works.append(SpinozaWork(n.title, en_text, la_text))

    return ExtractResult(works=works, toc_titles=found)
