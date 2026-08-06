"""Registry delle fonti. pd_year = anno in cui l'EDIZIONE entra in pubblico dominio,
non l'autore: per un testo PD è la traduzione/apparato a essere protetto."""
from __future__ import annotations

import os
from dataclasses import dataclass

# Sovrascrivibile via env: gli adapter bespoke di M1b (cartesio, rousseau,
# nietzsche, ortega) non devono restare saldati a un percorso di una sola
# macchina. Il default resta questo, invariato.
RAW_ROOT = os.environ.get(
    "PHILOSOPHY_RAW_ROOT", r"E:/giovanni/Dropbox/remotedir/libri/notebooklm"
)


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    adapter: str
    lang: str
    edizione: str
    traduttore: str | None
    anno_edizione: int | None
    pd_year: int
    glob: str = "*_part*.txt"


def _delphi(key: str, name: str, anno: int) -> Source:
    return Source(
        key=key, name=name, adapter="delphi", lang="en",
        edizione="Delphi Classics", traduttore=None,
        anno_edizione=anno, pd_year=1900,
    )


SOURCES: dict[str, Source] = {
    s.key: s
    for s in [
        # Delphi: traduzioni ottocentesche PD. pd_year=1900 = già PD.
        _delphi("seneca", "Seneca", 2014),
        _delphi("pascal", "Pascal", 2000),
        _delphi("marx", "Marx", 2000),
        _delphi("hegel", "Hegel", 2000),
        _delphi("kant", "Kant", 2000),
        _delphi("hume", "Hume", 2000),
        _delphi("locke", "Locke", 2000),
        _delphi("lucretius", "Lucretius", 2000),
        # Non-Delphi: adapter bespoke, piano successivo.
        # Originale francese (Arvensa, epub): Descartes muore nel 1650, nessun
        # traduttore di mezzo -> traduttore=None. pd_year=1900 = gia' PD (il
        # "Copyrights Arvensa Editions" nei metadata e' boilerplate su un
        # testo di pubblico dominio, non protegge l'originale).
        Source("cartesio", "Descartes", "cartesio", "fr",
               "Arvensa Editions", None, 2015, 1900, glob="*.epub"),
        Source("rousseau", "Rousseau", "rousseau", "fr",
               "Arvensa Editions", None, None, 1900),
        # Originale tedesco: Nietzsche † 1900 -> PD dal 1971, nessun traduttore
        # di mezzo. Anaconda dichiara "Alle Rechte vorbehalten" ma è boilerplate
        # su testo PD; §70 UrhG richiede lavoro critico che una ristampa non ha.
        Source("nietzsche", "Nietzsche", "nietzsche", "de",
               "Anaconda Verlag", None, 2013, 1971, glob="*.epub"),
        # Originale tedesco: Schopenhauer † 1860 -> PD, nessun traduttore di
        # mezzo. La ristampa "Gesammelte Werke" dichiara "Alle Rechte
        # vorbehalten" ma e' boilerplate su testo PD (stesso caso Nietzsche/
        # Anaconda). Copertura PARZIALE (WWR I+II + selezione, non l'opera
        # omnia): i buchi (vierfache Wurzel, Grundprobleme der Ethik, Parerga)
        # sono un ingest successivo da Zeno.org. Vedi schopenhauer.py.
        Source("schopenhauer", "Schopenhauer", "schopenhauer", "de",
               "Gesammelte Werke (ristampa di testo PD)", None, 2014, 1900,
               glob="*.epub"),
        # Delphi Classics, epub. Leibniz † 1716: originali FR/LA in traduzioni
        # inglesi d'epoca tutte PD (Hedge 1867, Montgomery 1908, Haldane, Latta
        # 1898, Duncan 1890 — pre-1929). traduttore per-opera, None a livello
        # di Source. Solo testo d'autore; apparato "The Criticism"+ scartato.
        # Vedi leibniz.py.
        Source("leibniz", "Leibniz", "leibniz", "en",
               "Delphi Classics", None, 2025, 1900, glob="*.epub"),
        Source("ortega", "Ortega y Gasset", "ortega", "es",
               "Obras completas — Fundación Ortega y Gasset", None, None, 2026),
        # Originale greco, traduzioni inglesi PD (Oxford/Loeb-era, 1908-1935 ca.):
        # Aristotele muore 322 a.C., nessun copyright sull'originale possibile.
        # Delphi mette un traduttore DIVERSO per (quasi) ogni opera (Ross,
        # Jowett, Butcher, Owen, Edghill...): traduttore=None qui a livello di
        # Source, valorizzato per-opera in aristotle.py (Work.traduttore),
        # verificato leggendo la riga "Translated by X" di ciascuna, mai
        # assunto. pd_year=1900: le traduzioni Oxford (~1908-1931) sarebbero
        # protette fino a ~70 anni dalla morte del traduttore, ma tutte
        # risultano gia' su archive.org/gutenberg come PD (pubblicazione
        # pre-1929 e traduttori morti da decenni); non verificato caso per
        # caso quanto i pd_year espliciti degli altri Delphi, quindi 1900 e'
        # qui la convenzione "gia' PD" ereditata dagli altri _delphi(), non
        # un anno accertato voce per voce.
        Source("aristotle", "Aristotle", "aristotle", "en",
               "Delphi Classics", None, 2013, 1900, glob="*.epub"),
        # Originale PDF (non txt/epub, unico adapter che apre un PDF), edizione
        # CCEL: pagina indice 1 del PDF dichiara "Rights: Public Domain" senza
        # condizioni; pagina indice 152 identifica traduzione e stampa (vedi
        # docstring aquinas.py per la prova completa). pd_year=1925 = fine
        # pubblicazione a scaglioni della traduzione originale (1911-1925),
        # la ristampa Benziger 1947 citata nel PDF e' la stessa traduzione.
        Source("aquinas", "Aquinas", "aquinas", "en",
               "Benziger Bros. edition, 1947 (CCEL digital text)",
               "Fathers of the English Dominican Province", 1947, 1925,
               glob="Summa Theologica*.pdf"),
        # Delphi, epub: stessa cartella sorgente dell'epub gemello di
        # Aristotele, ma copiato in una RAW_ROOT/plato/ dedicata (non un
        # filtro sul nome) cosi' il glob "*.epub" non puo' mai pescare
        # l'epub di Aristotele. Traduttore Jowett (morto 1893, PD) verificato
        # leggendo la riga "Translated by X" di OGNI dialogo pubblicato, non
        # solo del primo: Delphi mescola 5 traduttori in questo epub (Lamb e
        # Bury sono Loeb Classical Library, non "gia' PD" come Jowett) --
        # vedi docstring plato.py per l'elenco completo ed esclusioni.
        # pd_year=1900 = gia' PD.
        Source("plato", "Plato", "plato", "en",
               "Delphi Classics", "Benjamin Jowett", 2012, 1900, glob="*.epub"),
        # Serie ottocentesca Nicene and Post-Nicene Fathers (Schaff, 1886-1890),
        # epub 'Complete Works' Patristic Publishing 2019 che la ricompila e
        # dichiara essa stessa "public domain" (vedi docstring augustine.py).
        # Molti traduttori vittoriani (Pilkington, Dods, Holmes...): traduttore
        # None a livello di Source, provenienza in `edizione`. pd_year=1890 =
        # gia' PD. Agostino † 430: nessun copyright possibile sull'originale.
        Source("augustine", "Augustine", "augustine", "en",
               "Nicene and Post-Nicene Fathers, Series I (P. Schaff ed., "
               "1886-1890; Patristic Publishing digital ed. 2019)",
               None, 1890, 1890, glob="*.epub"),
        # Delphi Classics, epub. Traduzione Elwes (1883-84) per Ethics/TTP/
        # Political Treatise/Emendation/Letters, Wolf (1910) per il Breve
        # Trattato: tutte PD (NON Curley/Shirley, moderne e assenti). Spinoza
        # † 1677. Le 4 opere con originale latino a fronte danno i gemelli
        # .la.md degli atomi (rappresentazione `la`); vedi spinoza.py.
        Source("spinoza", "Spinoza", "spinoza", "en",
               "Delphi Classics", "R. H. M. Elwes / A. Wolf", 2019, 1900,
               glob="*.epub"),
        # Delphi Classics, epub. Hobbes † 1679: originali inglesi PD, opere
        # latine (De Cive, De Corpore) in traduzione inglese d'epoca PD. Solo
        # il nucleo filosofico (vedi hobbes.INCLUDE_PREFIXES); niente latino a
        # fronte per il corpus filosofico. pd_year=1900.
        Source("hobbes", "Hobbes", "hobbes", "en",
               "Delphi Classics", None, 2019, 1900, glob="*.epub"),
    ]
}
# Dávila: escluso. Traduzioni italiane Krisis protette (~2065), nessun
# originale accessibile. Analogo di EXCLUDE_AUTHORS (Hemingway) in English.


def delphi_sources() -> list[Source]:
    return [s for s in SOURCES.values() if s.adapter == "delphi"]
