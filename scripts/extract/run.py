# scripts/extract/run.py
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .aquinas import extract as aquinas_extract
from .aquinas import find_pdf as aquinas_find_pdf
from .augustine import extract as augustine_extract
from .augustine import find_epub as augustine_find_epub
from .spinoza import extract as spinoza_extract
from .spinoza import find_epub as spinoza_find_epub
from .hobbes import extract as hobbes_extract
from .hobbes import find_epub as hobbes_find_epub
from .aristotle import extract as aristotle_extract
from .aristotle import find_epub as aristotle_find_epub
from .aristotle_pd import run_aristotle_pd
from .cartesio import extract as cartesio_extract
from .common import Work, load_raw, write_work
from .delphi import extract
from .delphi_toc import parse_toc
from .marx_kant_pd import run_marx_kant_pd
from .nietzsche import extract as nietzsche_extract
from .nietzsche import find_epub as nietzsche_find_epub
from .schopenhauer import extract as schopenhauer_extract
from .schopenhauer import find_epub as schopenhauer_find_epub
from .leibniz import extract as leibniz_extract
from .leibniz import find_epub as leibniz_find_epub
from .ortega import run_ortega as ortega_run_ortega
from .plato import extract as plato_extract
from .plato import find_epub as plato_find_epub
from .rousseau import extract as rousseau_extract
from .rousseau_toc import parse_toc as rousseau_parse_toc
from .seneca_pd import run_seneca_pd
from .sources import SOURCES, Source, delphi_sources

# parents[3] e non [2]: da quando scripts/ vive dentro quartz-philosophy/, il
# vault e' FRATELLO della dir del sito, non dentro la stessa root. data/ invece
# si e' spostata insieme agli script, quindi resta a parents[2].
VAULT_ROOT = Path(__file__).resolve().parents[3] / "VaultPhilosophy"
STARTS_PATH = Path(__file__).resolve().parents[2] / "data" / "work_starts.json"


@dataclass
class SourceReport:
    key: str
    toc_publishable: int
    extracted: int
    missing: list[str] = field(default_factory=list)
    unmarked: list[str] = field(default_factory=list)
    skipped: int = 0
    # Opere il cui corpo ingloba il testo di voci `missing` (vedi
    # ortega.Contamination): un titolo non localizzato NON sparisce, il suo
    # testo resta incollato all'opera precedente. Senza dirlo, `missing` si
    # legge come "testi che non pubblichiamo" invece che "testi finiti nel
    # file sbagliato". Per ora lo popola solo ortega.
    contaminated: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (not self.missing and not self.unmarked
                and self.extracted + self.skipped == self.toc_publishable)


def load_starts(path: Path = STARTS_PATH) -> dict[str, dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_source(source: Source, starts: dict[str, dict],
               vault_root: Path = VAULT_ROOT) -> SourceReport:
    text = load_raw(source)
    toc_publishable = sum(1 for e in parse_toc(text) if e.kind in ("work", "latin"))
    source_starts = starts.get(source.key, {})
    result = extract(text, source, source_starts)
    for w in result.works:
        write_work(w, source, vault_root)
    # Conta solo gli skip PRESI dentro extract() (titolo in TOC E localizzato):
    # una riga "skip" bogus per un titolo assente dal TOC non deve gonfiare
    # il conteggio e mascherare un'opera davvero non pubblicata.
    return SourceReport(source.key, toc_publishable, len(result.works),
                        result.missing, result.unmarked, len(result.skipped))


def run_nietzsche(source: Source, vault_root: Path = VAULT_ROOT) -> SourceReport:
    """Adapter bespoke, non-Delphi: TOC epub, non lista di work_starts.json.
    Ogni voce del TOC e' gia' un'opera pubblicabile (nessun apparato dentro
    il TOC), quindi non ci sono missing/unmarked/skipped da tracciare come
    per i Delphi: extracted == toc_publishable e' l'unico segnale di 'ok'."""
    epub_path = nietzsche_find_epub(source)
    result = nietzsche_extract(epub_path)
    for w in result.works:
        write_work(w, source, vault_root)
    return SourceReport(source.key, len(result.toc_titles), len(result.works))


def run_schopenhauer(source: Source, vault_root: Path = VAULT_ROOT) -> SourceReport:
    """Come run_nietzsche: epub tedesco, confini d'opera espliciti in
    schopenhauer.WORKS (il TOC annidato non li delimita). I monconi d'apparato
    sono gia' scartati dall'adapter, quindi toc_titles == works pubblicate:
    extracted == toc_publishable e' il segnale di 'ok'."""
    epub_path = schopenhauer_find_epub(source)
    result = schopenhauer_extract(epub_path)
    for w in result.works:
        write_work(w, source, vault_root)
    return SourceReport(source.key, len(result.toc_titles), len(result.works))


def run_leibniz(source: Source, vault_root: Path = VAULT_ROOT) -> SourceReport:
    """Come run_hobbes: epub Delphi con INCLUDE_PREFIXES; leibniz.extract fa
    gia' il check EXPECTED_WORKS (fail-closed) e scarta l'apparato, quindi
    toc_titles == works pubblicate."""
    epub_path = leibniz_find_epub(source)
    result = leibniz_extract(epub_path)
    for w in result.works:
        write_work(w, source, vault_root)
    return SourceReport(source.key, len(result.toc_titles), len(result.works))


def run_aristotle(source: Source, vault_root: Path = VAULT_ROOT) -> SourceReport:
    """Adapter bespoke, non-Delphi: TOC epub a due livelli (sezioni + opere +
    apparato), le 46 opere attese sono un'asserzione esplicita
    (aristotle.EXPECTED_WORKS) come in cartesio.py. `missing` = opera attesa
    mai trovata nel TOC; `unmarked` = opera trovata nel TOC ma il confine
    blurb/corpo non e' stato localizzato (fail-closed, vedi aristotle.py)."""
    epub_path = aristotle_find_epub(source)
    result = aristotle_extract(epub_path)
    for w in result.works:
        write_work(w, source, vault_root)
    toc_publishable = len(result.works) + len(result.missing) + len(result.unmarked)
    return SourceReport(source.key, toc_publishable, len(result.works),
                        result.missing, result.unmarked)


def run_aquinas(source: Source, vault_root: Path = VAULT_ROOT) -> SourceReport:
    """Adapter bespoke, unico che legge un PDF (fitz/PyMuPDF) invece di
    txt/epub. I 31 trattati attesi sono un'asserzione esplicita
    (aquinas.TREATISES), verificata a mano leggendo l'intestazione reale di
    ognuno sul PDF (vedi docstring aquinas.py) - non dedotta dal solo TOC,
    che non elenca le suddivisioni interne non etichettate come "Treatise
    on" nel proprio indice. Nessun missing/unmarked possibile per
    costruzione (le pagine di inizio sono asserite, non cercate): extract()
    solleva ValueError fail-closed se una pagina risulta vuota o se il PDF
    ha meno pagine del previsto (struttura cambiata)."""
    pdf_path = aquinas_find_pdf(source)
    result = aquinas_extract(pdf_path)
    for w in result.works:
        write_work(w, source, vault_root)
    return SourceReport(source.key, len(result.toc_titles), len(result.works))


def run_augustine(source: Source, vault_root: Path = VAULT_ROOT) -> SourceReport:
    """Adapter bespoke, epub NPNF (Schaff). Il toc.ncx piatto elenca 29
    navPoint: 2 d'apparato (biografia+cronologia del curatore) scartati, 27
    opere pubblicabili asserite (augustine.EXPECTED_WORKS). Nessun
    missing/unmarked possibile per costruzione: extract() solleva ValueError
    fail-closed se i navPoint pubblicabili non sono esattamente 27 o se
    un'opera esce vuota dopo la pulizia dell'apparato."""
    epub_path = augustine_find_epub(source)
    result = augustine_extract(epub_path)
    for w in result.works:
        write_work(w, source, vault_root)
    return SourceReport(source.key, len(result.toc_titles), len(result.works))


def run_spinoza(source: Source, vault_root: Path = VAULT_ROOT) -> SourceReport:
    """Adapter bespoke, epub Delphi. Le 6 opere sono un'asserzione esplicita
    (spinoza.EXPECTED_WORKS): extract() solleva ValueError fail-closed se il
    TOC di primo livello non le porta esattamente. Qui si scrive in _raw solo
    l'INGLESE (kind=work): l'originale latino delle 4 opere che ce l'hanno
    diventa i gemelli .la.md degli atomi (vedi build_spinoza_latin_siblings)."""
    result = spinoza_extract(spinoza_find_epub(source))
    for w in result.works:
        write_work(Work(title=w.title, text=w.en_text, kind="work"), source, vault_root)
    return SourceReport(source.key, len(result.toc_titles), len(result.works))


def run_hobbes(source: Source, vault_root: Path = VAULT_ROOT) -> SourceReport:
    """Adapter bespoke, epub Delphi. Solo il nucleo filosofico (11 opere,
    hobbes.INCLUDE_PREFIXES): extract() solleva ValueError fail-closed se non
    ne estrae esattamente 11 (TOC cambiato). Tutto inglese: nessun gemello
    latino per il corpus filosofico."""
    result = hobbes_extract(hobbes_find_epub(source))
    for w in result.works:
        write_work(w, source, vault_root)
    return SourceReport(source.key, len(result.toc_titles), len(result.works))


def run_cartesio(source: Source, vault_root: Path = VAULT_ROOT) -> SourceReport:
    """Adapter bespoke arvensa/epub: le opere attese sono un'asserzione
    esplicita (cartesio.EXPECTED_WORKS), non dedotte dal TOC. `missing` qui
    segnala un'opera attesa mai trovata nel TOC; `unexpected_top` (voci
    top-level non classificate) e' appiattito dentro `unmarked` per riuso del
    report Delphi-style, cosi' fa comunque fallire `ok` se il TOC e' cambiato."""
    result = cartesio_extract(source)
    for w in result.works:
        write_work(w, source, vault_root)
    return SourceReport(source.key, len(result.found) + len(result.missing),
                        len(result.works), result.missing, result.unexpected_top)


def run_ortega(source: Source, vault_root: Path = VAULT_ROOT) -> SourceReport:
    """Adapter bespoke, non-Delphi: indice piatto per anno con apparato
    filologico corposo in coda a ogni tomo (vedi docstring ortega.py). A
    differenza di nietzsche, qui l'apparato E' mescolato nel flusso, quindi
    servono missing/skipped come per Delphi.

    Qui `missing` ha una conseguenza che negli altri adapter non c'e': il
    confine di un'opera e' l'inizio della successiva LOCALIZZATA, quindi il
    testo di una voce non localizzata resta incollato all'opera precedente
    invece di sparire. `contaminated` dice quali opere ne sono affette: senza,
    "N non localizzate" si leggerebbe come "N testi che non pubblichiamo"."""
    result = ortega_run_ortega(source, vault_root)
    return SourceReport(source.key, result.toc_publishable, len(result.works),
                        result.missing, [], len(result.skipped),
                        result.contaminated)


def run_plato(source: Source, vault_root: Path = VAULT_ROOT) -> SourceReport:
    """Adapter bespoke, non-Delphi standard: TOC epub, ma i confini di corpo
    NON si deducono dal solo TOC (troppi dialoghi sono orfani di voce-figlia,
    vedi docstring plato.py) -- si classifica l'HTML di ogni file nel range.
    I 30 dialoghi Jowett attesi sono un'asserzione esplicita
    (plato.EXPECTED_JOWETT_DIALOGUES) come in cartesio.py/aristotle.py.
    `missing` = dialogo atteso mai trovato nel TOC; `unmarked` qui e'
    `unexpected` (voce nello scope "The Translations".."The Spurious Works"
    che non e' ne' un dialogo Jowett atteso ne' un'esclusione nota per
    traduttore diverso -- segnale che il TOC e' cambiato)."""
    epub_path = plato_find_epub(source)
    result = plato_extract(epub_path)
    for w in result.works:
        write_work(w, source, vault_root)
    toc_publishable = len(result.works) + len(result.missing) + len(result.unexpected)
    return SourceReport(source.key, toc_publishable, len(result.works),
                        result.missing, result.unexpected)


def run_rousseau(source: Source, starts: dict[str, dict],
                 vault_root: Path = VAULT_ROOT) -> SourceReport:
    """Adapter bespoke Arvensa Editions: struttura a due livelli come
    Delphi (TOC + corpo con apparato misto: presentazione editoriale,
    biografie, atti giudiziari annessi...). Il confine STRUTTURALE
    (cascata di apertura "* * *", blocchi di navigazione ripetuti fra
    capitoli) si deduce ancora euristicamente (vedi rousseau.py); il
    confine CURATORIALE (introduzioni ottocentesche Musset-Pathay/
    Petitain davanti al vero testo di Rousseau) usa invece lo stesso
    contratto fail-closed di delphi.py via data/work_starts.json["rousseau"]."""
    text = load_raw(source)
    toc_publishable = sum(1 for e in rousseau_parse_toc(text) if e.kind in ("work", "letters"))
    source_starts = starts.get(source.key, {})
    result = rousseau_extract(text, source, source_starts)
    for w in result.works:
        write_work(w, source, vault_root)
    return SourceReport(source.key, toc_publishable, len(result.works),
                        result.missing, result.unmarked, len(result.skipped))


def format_report(reports: list[SourceReport]) -> str:
    lines = []
    for r in reports:
        mark = "OK  " if r.ok else "FAIL"
        skip_note = f" ({r.skipped} skip)" if r.skipped else ""
        lines.append(f"{mark} {r.key:12} {r.extracted}/{r.toc_publishable} opere{skip_note}")
        for t in r.missing:
            lines.append(f"       non localizzata: {t}")
        for t in r.unmarked:
            lines.append(f"       confine ignoto (non pubblicata): {t}")
        if r.contaminated:
            lines.append(
                f"       ATTENZIONE: {len(r.contaminated)} opere hanno il corpo "
                f"CONTAMINATO dal testo delle voci non localizzate qui sopra "
                f"(non sono testi mancanti: sono finiti nel file sbagliato)"
            )
            for t in r.contaminated:
                lines.append(f"         {t}")
    return "\n".join(lines)


def main() -> int:
    starts = load_starts()
    reports = [run_source(s, starts) for s in delphi_sources()]
    for line in run_marx_kant_pd():
        print(line)
    for line in run_seneca_pd():
        print(line)
    reports.append(run_nietzsche(SOURCES["nietzsche"]))
    reports.append(run_schopenhauer(SOURCES["schopenhauer"]))
    reports.append(run_leibniz(SOURCES["leibniz"]))
    reports.append(run_aristotle(SOURCES["aristotle"]))
    for line in run_aristotle_pd():
        print(line)
    reports.append(run_aquinas(SOURCES["aquinas"]))
    reports.append(run_augustine(SOURCES["augustine"]))
    reports.append(run_spinoza(SOURCES["spinoza"]))
    reports.append(run_hobbes(SOURCES["hobbes"]))
    reports.append(run_cartesio(SOURCES["cartesio"]))
    reports.append(run_ortega(SOURCES["ortega"]))
    reports.append(run_rousseau(SOURCES["rousseau"], starts))
    reports.append(run_plato(SOURCES["plato"]))
    print(format_report(reports))
    return 0 if all(r.ok for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
