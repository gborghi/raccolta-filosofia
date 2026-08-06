# scripts/extract/ortega.py
"""Adapter bespoke per Ortega y Gasset — "Obras completas" (Fundación José
Ortega y Gasset / Taurus, edizione digitale megustaleer). NON riusa delphi.py:
la struttura del sorgente è del tutto diversa (indice piatto per anno, non
sezioni chiuse). Verificato leggendo tutti e 5 i tomi, non un campione.

STRUTTURA DEL SORGENTE GREZZO
------------------------------
I file part1..part8 sono spezzoni da ~1500 righe ("Parte NN di 40") concatenati
con marker `===== INIZIO/FINE FILE: ... Tomo <ROMANO> - Parte NN di 40.txt
=====`. L'ordine dei tomi nel flusso NON è I,II,III,IV,V ma III, II, IV, I, V
(verificato via grep dei marker su tutti gli 8 file) — ma ogni tomo è
internamente contiguo (le sue 40 parti si susseguono), quindi basta
segmentare sul marker "Parte 01 di 40" di ciascun tomo: non serve riordinare.

Ogni tomo ripete IDENTICO questo scheletro (pubblicità megustaleer, credits
Fundación José Ortega y Gasset, poi):

    ÍNDICE
    Obras completas. Tomo <N> (<anni>)
    Advertencia a la edición digital        <- apparato, front
    Esta edición…                           <- apparato, front
    <anno 19NN>                             <- separatore, non un'opera
      <titolo opera 1>
      <titolo opera 2>
      ...
    NOTAS A LA EDICIÓN                      <- SENTINELLA: da qui fino a fine
    NOTICIA BIBLIOGRÁFICA                      tomo è TUTTO apparato filologico
    APÉNDICE                                   (note edizione, bibliografia,
    ANEXOS                                     varianti, indici onomastico/
    ÍNDICE ONOMÁSTICO                          toponomastico/analitico
    ÍNDICE TOPONÍMICO                          dell'INTERA opera omnia,
    ÍNDICES GENERALES                          cronologia, crediti — enorme:
    Cronología del Corpus textual              in Tomo III è ~il 60% delle
    Índice alfabético de títulos               righe del tomo)
    Índice de conceptos...
    Sobre este libro
    Créditos

Confermato dal testo stesso dell'edizione (corpo di "Esta edición…"): "...se ha
decidido mantener en la presente edición digital el enjundioso aparato
crítico que acompaña a cada tomo de la edición impresa (Notas a la edición,
Noticia bibliográfica, Apéndice de variantes, Anexos, Índice onomástico,
Índice toponímico), añadiendo a cada tomo la Cronología del corpus textual...".
Per questo la regola è: appena l'indice incontra "NOTAS A LA EDICIÓN" si
smette di raccogliere voci pubblicabili — tutto il resto, incluso ANEXOS (che
talvolta contiene testi extra attribuiti a Ortega), viene scartato: è la
stessa edizione a classificarlo come apparato e non corpus (fail-closed).

Dentro alla zona pubblicabile, le voci dell'indice hanno 3 livelli:
  - contenitori di SERIE (es. "EL ESPECTADOR (1916-1934)", "EL ESPECTADOR I
    (1916)", "ENSAYOS DE CRÍTICA"): compaiono nel corpo come intestazione ma
    senza testo proprio prima della prossima intestazione — scartati
    automaticamente dal filtro "corpo vuoto" (MIN_BODY_LEN); le loro foglie
    restano opere separate (vedi LIBRI vs SERIE qui sotto).
  - capitoli/parti (marcatori romani "I." "II.", arabi "1." "2.", oppure
    "Primera parte:", "Segunda parte:"): NON diventano voci separate — non
    vengono cercati nel corpo, quindi il testo fra un titolo vero e il
    successivo li include per costruzione (restano dentro l'opera madre).
  - foglie reali (articoli, saggi, libri): un file per voce.

LIBRI vs SERIE (vedi PREFACE_TITLE_RE, parse_toc `capitolata`, book_head)
-------------------------------------------------------------------------
Alcuni contenitori a corpo vuoto NON sono serie ma LIBRI (monografie: "LA
REBELIÓN DE LAS MASAS", "ESPAÑA INVERTEBRADA", "EL TEMA DE NUESTRO TIEMPO",
"MEDITACIONES DEL QUIJOTE"). Scartarli come contenitori-serie e' un bug: il
loro corpo comincia con la PREFAZIONE (prima foglia), e siccome i loro
capitoli sono marcatori-figli NON localizzati, quella prefazione inghiotte
l'INTERO libro — che finiva pubblicato sotto il titolo della sua prefazione
("Prólogo para franceses" = tutta La rebelión de las masas, ecc.).

La distinzione e' STRUTTURALE, non tipografica (nel corpo un contenitore-serie
e un contenitore-libro sono identici: intestazione + righe vuote + intestazione
successiva). Il segnale affidabile e' nell'INDICE:
  - un contenitore-SERIE ha come prima foglia un ARTICOLO/saggio indipendente
    (mai una prefazione); le sue foglie sono opere a se'. Puo' contenere una
    foglia interna capitolata ("Ideas sobre Pío Baroja" con sezioni I..XV in
    ENSAYOS DE CRÍTICA) — ma resta serie perche' la PRIMA foglia non e' una
    prefazione.
  - un contenitore-LIBRO ha come prima foglia una PREFAZIONE di apertura
    (_is_preface: Prólogo/Advertencia/Lector…/Prefacio…) e, nella "run" di
    foglie consecutive (prefazioni + voci `capitolata`), almeno un capitolo
    con marcatori-figli. Allora si promuove: contenitore + run = UN'unica
    opera intitolata al contenitore, con la prefazione come prima parte; il
    confine finale resta l'inizio della prima foglia FUORI dalla run.
Regola tenuta STRETTA di proposito (una regola sbagliata e' costosa e
silenziosa): richiedere insieme prefazione-di-apertura E capitoli-figli
esclude ogni serie (zero falsi positivi verificati sui 5 tomi). Restano NON
promossi, come residuo onesto, i libri che questa struttura non marca: quelli
senza prefazione o senza capitoli-figli (le loro sezioni sono foglie piatte,
indistinguibili da una serie) — "LA DESHUMANIZACIÓN DEL ARTE E IDEAS SOBRE
LA NOVELA", "LAS ATLÁNTIDAS", "PERSONAS, OBRAS, COSAS", "GOETHE DESDE DENTRO",
"ENSIMISMAMIENTO Y ALTERACIÓN", "IDEAS Y CREENCIAS": restano scartati/dispersi
come prima, senza inventare un segnale che non c'e'.

Il corpo tipografa SEMPRE i titoli in MAIUSCOLO, anche quando l'indice li
scrive in maiuscolo/minuscolo misto ("Más, más ministros" in indice ->
"MÁS, MÁS MINISTROS" in corpo): il confronto usa .upper() su entrambi i lati
(mai case-sensitive puro come delphi_body — qui non funzionerebbe).

INTESTAZIONI SU PIÙ RIGHE (vedi HEADING_SPAN_MAX / _join_key)
-------------------------------------------------------------
L'indice scrive il titolo su UNA riga, unendo rubrica e sottotitolo con la
punteggiatura (",", ".—", "—", ".", ":", parentesi); il corpo invece li
tipografa su RIGHE DISTINTE separate da righe vuote, e la punteggiatura di
giunzione NON viene riprodotta. Esempio reale (Tomo IV):

    corpo:   "EL OBISPO LEPROSO" / <vuote> / "NOVELA, POR GABRIEL MIRÓ"
    indice:  "El obispo leproso, novela, por Gabriel Miró"

Perciò un titolo dell'indice può corrispondere a N righe non vuote CONSECUTIVE
del corpo (le righe vuote in mezzo si ignorano), la cui concatenazione —
normalizzata da _norm — coincide col titolo normalizzato. Il confronto resta
ESATTO: si accetta il match o sulla concatenazione normalizzata tale e quale,
o su _join_key (che neutralizza la sola punteggiatura di giunzione, uguale su
entrambi i lati). Mai un match parziale/fuzzy: un titolo ritrovato nel posto
sbagliato taglia l'opera a un confine falso e il conteggio sembra pure
migliorato — molto peggio di un "missing" dichiarato.

Lo span è limitato a HEADING_SPAN_MAX righe e non può attraversare una riga
che _norm riduce a stringa vuota (riga di solo anno fra parentesi come
"(1916-1934)", o solo richiamo di nota): senza questo divieto lo span
inghiottirebbe quella riga a costo zero e l'intestazione risulterebbe
ancorata più in alto del vero (verificato: "EL ESPECTADOR I (1916)" veniva
agganciato 6 righe prima, sulla riga "(1916-1934)" del contenitore).

Restano NON localizzabili (giustamente "missing", vedi report) due forme che
si potrebbero agganciare solo allentando il confronto:
  - rubrica e sottotitolo separati nel corpo da una riga di LUOGO E DATA
    ("Madrid, junio de 1927"), che spezza la contiguità dello span;
  - intestazioni "a esordio" (run-in), stampate in testa al paragrafo di prosa
    e non su una riga propria: "LA DIFICULTAD DE LA FILOSOFÍA.— La famosa
    dificultad atribuida a los estudios..." (sottosezioni del "Prólogo a
    Historia de la Filosofía, de Karl Vorländer").
Entrambe richiederebbero di saltare righe arbitrarie dentro lo span o di fare
prefix-match sulla prosa: esattamente il modo in cui `pos` si desincronizza.

CONTAMINAZIONE (vedi TomoExtract.contaminated)
----------------------------------------------
Un titolo non localizzato non sparisce e basta: siccome il confine di un'opera
è l'inizio dell'opera SUCCESSIVA LOCALIZZATA, il suo testo resta incollato in
coda all'opera che lo precede. `missing` da solo non lo dice, e il lettore del
report leggerebbe "N non localizzate" come "N testi che non pubblichiamo".
Per questo ogni opera porta l'elenco dei titoli inghiottiti nel proprio span.

DECISIONI (vedi anche report finale):
  - ANEXOS scartato in blocco, anche se a volte contiene testo firmato Ortega
    (l'edizione stessa lo classifica come apparato, non corpus principale).
  - Titoli duplicati nello stesso tomo (rubriche giornalistiche che ricorrono
    su più anni, es. "Hacia una mejor política"): la ricerca posizionale
    (posizione che avanza, come delphi_body) li assegna nell'ordine corretto;
    per lo slug, in caso di collisione, si aggiunge l'anno fra parentesi e,
    se ancora in collisione, un contatore.
  - Titoli lunghissimi (rari, senza em-dash da tagliare): troncati a
    TITLE_MAX_LEN caratteri per tenere gli slug corti (MAX_PATH Windows).
"""
from __future__ import annotations

import glob
import re
from dataclasses import dataclass, field
from pathlib import Path

from .common import Work, slugify, write_work
from .sources import RAW_ROOT, Source

MARKER_RE = re.compile(
    r"===== (?:INIZIO|FINE) FILE: Obras completas\. Tomo (\w+) - Parte (\d+) di (\d+)\.txt =====[ \t]*\n?"
)
TOMO_START_RE = re.compile(
    r"===== INIZIO FILE: Obras completas\. Tomo (\w+) - Parte 01 di \d+\.txt ====="
)
TOMO_HEADER_RE = re.compile(r"^Obras completas\.\s*Tomo\s+(\w+)\s*\(([^)]+)\)")

YEAR_RE = re.compile(r"^\d{4}$")
# Marcatore romano di capitolo/parte: token 1-6 caratteri SOLO da IVXLCDM
# (maiuscolo — parole reali come "Idea" non ci finiscono mai dentro),
# opzionale punto, opzionale sottotitolo.
ROMAN_CHILD_RE = re.compile(r"^[IVXLCDM]{1,6}\.?(\s+.*)?$")
ARABIC_CHILD_RE = re.compile(r"^\d{1,3}\.(\s+.*)?$")
ORDINAL_PARTE_RE = re.compile(
    r"^(Primera|Segunda|Tercera|Cuarta|Quinta|Sexta|S[eé]ptima|Octava|Novena|D[eé]cima)"
    r"\s+[Pp]arte\b"
)
# Titoli di apertura (front matter) di un LIBRO: prologo, avvertenza, prefazio,
# dedica, l'apostrofe "Lector…" delle Meditaciones. Applicato a stringa GIA'
# normalizzata da _norm (MAIUSCOLO). Serve solo a distinguere un contenitore-
# libro da un contenitore-serie: la prima foglia di un libro e' la sua
# prefazione (poi i capitoli sono marcatori-figli), quella di una serie (EL
# ESPECTADOR, ENSAYOS DE CRÍTICA) e' un articolo/saggio, mai una prefazione.
# Tenuto STRETTO di proposito: "Epílogo" e "Introducción" NON ci sono
# (l'epilogo chiude, non apre; "Introducción a una estimativa" e' un'opera).
PREFACE_TITLE_RE = re.compile(
    r"^(PR[ÓO]LOGO|ADVERTENCIA|PREFACIO|PROEMIO|DEDICATORIA|"
    r"AL LECTOR\b|LECTOR\b|NOTA PRELIMINAR|A MODO DE PR[ÓO]LOGO)"
)

FRONT_APPARATUS_PREFIXES = ("ADVERTENCIA A LA EDICIÓN DIGITAL", "ESTA EDICIÓN")
TAIL_SENTINEL = "NOTAS A LA EDICIÓN"

MIN_BODY_LEN = 20   # sotto: intestazione-contenitore senza testo proprio (skip)
TITLE_MAX_LEN = 90  # oltre: tronca per slug corti (MAX_PATH Windows)
HEADING_SPAN_MAX = 4  # righe non vuote max per una sola intestazione dell'indice


@dataclass
class Contamination:
    """Un'opera pubblicata il cui corpo ingloba il testo di voci dell'indice
    non localizzate (vedi docstring, sezione CONTAMINAZIONE): il confine
    dell'opera è l'inizio della successiva LOCALIZZATA, quindi il testo delle
    voci saltate finisce in coda a `work`. Va detto nel report, non dedotto."""
    work: str              # titolo dell'opera che ha inglobato il testo
    swallowed: list[str]   # titoli dell'indice finiti dentro `work`
    work_index: int = -1   # posizione in TomoExtract.works (per risincronizzare
                           # `work` dopo _dedupe, che puo' rinominare l'opera)


@dataclass
class TomoExtract:
    label: str                 # es. "Tomo III (1917-1925)"
    works: list[Work] = field(default_factory=list)
    toc_publishable: int = 0
    missing: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    contaminated: list[Contamination] = field(default_factory=list)


@dataclass
class ExtractResult:
    tomos: list[TomoExtract] = field(default_factory=list)

    @property
    def works(self) -> list[Work]:
        return [w for t in self.tomos for w in t.works]

    @property
    def toc_publishable(self) -> int:
        return sum(t.toc_publishable for t in self.tomos)

    @property
    def missing(self) -> list[str]:
        return [f"{t.label}: {m}" for t in self.tomos for m in t.missing]

    @property
    def skipped(self) -> list[str]:
        return [f"{t.label}: {s}" for t in self.tomos for s in t.skipped]

    @property
    def contaminated(self) -> list[str]:
        return [
            f"{t.label}: «{c.work}» ingloba il testo di: " + "; ".join(c.swallowed)
            for t in self.tomos for c in t.contaminated
        ]


FOOTNOTE_SUFFIX_RE = re.compile(r"(\s*\[\d{1,4}\])+\s*$")
# Le voci-contenitore di serie ("EL ESPECTADOR (1916-1934)", "EL ESPECTADOR
# I (1916)") portano l'anno fra parentesi SOLO nell'indice: nel corpo
# l'intestazione e' spoglia ("EL ESPECTADOR", "EL ESPECTADOR I"). Tolto da
# entrambi i lati per il confronto (mai dal titolo pubblicato).
YEAR_PAREN_SUFFIX_RE = re.compile(r"\s*\(\d{4}(?:-\d{4})?\)\s*$")
# "X.— Y" nell'indice a volte diventa "X— Y" nel corpo (il punto prima
# della lineetta sparisce quando la frase finisce gia' con "?" o "!").
DOT_DASH_RE = re.compile(r"\.\s*([—–])")
# Punteggiatura con cui l'INDICE unisce rubrica e sottotitolo su una riga sola
# e che il CORPO non riproduce quando li tipografa su righe distinte. Serve
# solo a confrontare: si neutralizza su entrambi i lati, mai sul titolo
# pubblicato. NON e' un match fuzzy — resta richiesta l'uguaglianza totale
# della concatenazione, non un prefisso.
JOIN_PUNCT_RE = re.compile(r"[.,;:—–()]+")


def _norm(line: str) -> str:
    """Normalizza per il confronto TOC<->corpo. Il corpo incolla talvolta un
    richiamo di nota alla fine dell'intestazione, senza spazio (es.
    "LA PEDAGOGÍA SOCIAL COMO PROGRAMA POLÍTICO[7]"): senza toglierlo, il
    confronto esatto fallisce, la ricerca posizionale salta oltre l'opera
    reale e trova per caso un'occorrenza sbagliata molto più avanti (dentro
    l'apparato "Notas a la edición", che ripete i titoli come sotto-voce) —
    da lì in poi `pos` e' desincronizzato e TUTTE le opere successive
    risultano false "missing" a cascata. Scoperto solo testando, non
    documentato altrove."""
    s = line.strip()
    s = FOOTNOTE_SUFFIX_RE.sub("", s)
    s = YEAR_PAREN_SUFFIX_RE.sub("", s)
    s = DOT_DASH_RE.sub(r"\1", s)
    return re.sub(r"\s+", " ", s).upper()


def load_tomo_blobs(source: Source) -> list[str]:
    """Blob grezzi per tomo (marker INIZIO/FINE FILE ancora presenti — servono
    per la segmentazione), nell'ordine di apparizione nel flusso (non
    nell'ordine numerico dei tomi)."""
    pattern = str(Path(RAW_ROOT) / source.key / source.glob)
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"nessun file per {source.key}: {pattern}")
    text = "\n".join(
        Path(p).read_text(encoding="utf-8", errors="replace") for p in paths
    )
    starts = [m.start() for m in TOMO_START_RE.finditer(text)]
    if not starts:
        raise ValueError(f"nessun marker di inizio tomo trovato per {source.key}")
    starts.append(len(text))
    return [text[starts[i]:starts[i + 1]] for i in range(len(starts) - 1)]


def _strip_markers(text: str) -> str:
    return MARKER_RE.sub("", text)


def _is_front_apparatus(line_upper: str) -> bool:
    return any(line_upper.startswith(p) for p in FRONT_APPARATUS_PREFIXES)


def _is_child_marker(line: str) -> bool:
    return bool(
        ROMAN_CHILD_RE.match(line)
        or ARABIC_CHILD_RE.match(line)
        or ORDINAL_PARTE_RE.match(line)
    )


def _is_preface(title: str) -> bool:
    """Il titolo e' una prefazione di apertura di libro? Confronto su _norm."""
    return bool(PREFACE_TITLE_RE.match(_norm(title)))


def parse_toc(lines: list[str]) -> tuple[int, int, str, list[tuple[str, str, bool]]]:
    """Ritorna (indice ÍNDICE, indice di fine blocco-indice, etichetta tomo,
    lista (anno_corrente, titolo, capitolata)) per le sole voci pubblicabili —
    apparato front/tail e separatori/figli esclusi. `anno_corrente` è l'ultimo
    anno incontrato, usato solo per disambiguare titoli duplicati nello stesso
    tomo. `capitolata` = la voce è seguita nell'indice da un marcatore-figlio
    (romano/arabo/"Primera parte:"), cioè ha capitoli propri: serve solo alla
    promozione libro/serie in extract_tomo (una serie ha voci-foglia
    indipendenti, un libro ha capitoli come figli — vedi docstring modulo).
    L'indice di fine-blocco è dove si è fermato il parsing (la riga
    "NOTAS A LA EDICIÓN" DENTRO L'INDICE, non nel corpo): la ricerca del
    corpo deve partire da lì, non da `idx_start` — altrimenti la prima
    occorrenza di ogni titolo che si trova è quella nell'indice stesso
    (breve, adiacente alla successiva), non l'intestazione vera nel corpo."""
    idx_start = next(i for i, l in enumerate(lines) if l.strip() == "ÍNDICE")
    label = "?"
    for raw in lines[idx_start + 1: idx_start + 6]:
        m = TOMO_HEADER_RE.match(raw.strip())
        if m:
            label = f"Tomo {m.group(1)} ({m.group(2)})"
            break

    entries: list[tuple[str, str, bool]] = []
    year = ""
    toc_end = len(lines)
    for i, raw in enumerate(lines[idx_start + 1:], start=idx_start + 1):
        line = raw.strip()
        if not line:
            continue
        up = line.upper()
        if up == TAIL_SENTINEL:
            toc_end = i
            break
        if TOMO_HEADER_RE.match(line):
            continue
        if _is_front_apparatus(up):
            continue
        if YEAR_RE.match(line):
            year = line
            continue
        if _is_child_marker(line):
            # Un marcatore-figlio marca "capitolata" l'ultima voce vera vista:
            # i figli seguono sempre il loro genitore nell'indice (righe vuote
            # a parte). Idempotente su figli consecutivi.
            if entries:
                y, t, _ = entries[-1]
                entries[-1] = (y, t, True)
            continue
        entries.append((year, line, False))
    return idx_start, toc_end, label, entries


def _join_key(normalized: str) -> str:
    """Chiave di confronto insensibile alla sola punteggiatura di giunzione.
    Da applicare a una stringa GIA' passata per _norm."""
    return re.sub(r"\s+", " ", JOIN_PUNCT_RE.sub(" ", normalized)).strip()


def find_heading(lines: list[str], title: str, start: int, end: int | None = None) -> int | None:
    """Match esatto su UNA riga. Usato per le sentinelle strutturali
    ("ADVERTENCIA A LA EDICIÓN DIGITAL", TAIL_SENTINEL), che nel corpo stanno
    sempre su una riga propria. Per i titoli delle opere usare
    find_heading_span, che copre anche le intestazioni su piu' righe."""
    target = _norm(title)
    stop = len(lines) if end is None else end
    for i in range(start, stop):
        if _norm(lines[i]) == target:
            return i
    return None


def _heading_spans(lines: list[str], i: int, end: int):
    """Genera (concatenazione_normalizzata, indice_dopo_lo_span) per gli span
    di 1..HEADING_SPAN_MAX righe non vuote a partire da i. Le righe vuote fra
    una riga e l'altra si ignorano; una riga che _norm riduce a vuoto (solo
    anno fra parentesi, solo richiamo di nota) INTERROMPE lo span invece di
    essere assorbita a costo zero: e' contenuto reale, non parte del titolo."""
    parts: list[str] = []
    j = i
    while j < end and len(parts) < HEADING_SPAN_MAX:
        raw = lines[j]
        if not raw.strip():
            j += 1
            continue
        norm = _norm(raw)
        if not norm:
            return
        parts.append(norm)
        j += 1
        yield " ".join(parts), j


def find_heading_span(lines: list[str], title: str, start: int,
                      end: int) -> tuple[int, int] | None:
    """Cerca `title` come intestazione su 1..HEADING_SPAN_MAX righe del corpo.
    Ritorna (riga_iniziale_intestazione, riga_iniziale_corpo) o None.
    Il corpo dell'opera comincia DOPO l'ultima riga dell'intestazione, non
    dopo la prima: con un titolo su due righe, partire da riga+1 lascerebbe
    il sottotitolo dentro al testo."""
    target = _norm(title)
    if not target:
        return None
    target_key = _join_key(target)
    for i in range(start, end):
        if not lines[i].strip() or not _norm(lines[i]):
            continue
        for cat, after in _heading_spans(lines, i, end):
            if cat == target or _join_key(cat) == target_key:
                return i, after
    return None


def _shorten(title: str) -> str:
    if len(title) <= TITLE_MAX_LEN:
        return title
    cut = title[:TITLE_MAX_LEN].rsplit(" ", 1)[0]
    return cut or title[:TITLE_MAX_LEN]


def extract_tomo(blob: str) -> TomoExtract:
    clean = _strip_markers(blob)
    lines = clean.split("\n")
    idx_start, toc_end, label, entries = parse_toc(lines)

    # Il corpo comincia dopo la ripetizione (in MAIUSCOLO) di "Advertencia a
    # la edición digital", che segue l'intera coda di apparato nell'indice.
    # La ricerca DEVE partire da toc_end (dove si e' fermato parse_toc), non
    # da idx_start: altrimenti la prima occorrenza trovata e' quella dentro
    # l'indice stesso (mixed-case ma identica una volta normalizzata).
    body_start = find_heading(lines, "ADVERTENCIA A LA EDICIÓN DIGITAL", toc_end)
    if body_start is None:
        # fallback robusto: prima riga "lunga" (prosa) dopo l'indice.
        body_start = next(
            (i for i in range(toc_end, len(lines)) if len(lines[i].strip()) > 150),
            toc_end,
        )
    # Confine di SICUREZZA calcolato UNA VOLTA SOLA, PRIMA di cercare le
    # opere: senza, un titolo che non si trova nella sua posizione vera (per
    # una differenza tipografica minima fra indice e corpo — un punto prima
    # di una lineetta, un titolo composto reso diversamente...) puo' essere
    # ritrovato per caso molto piu' avanti, DENTRO "Notas a la edición"
    # (l'apparato spesso ripete/elenca gli stessi titoli). Da quel match
    # sbagliato in poi `pos` resta desincronizzato e OGNI opera successiva,
    # anche quelle perfettamente presenti, risulta falsamente "missing" a
    # cascata. Scoperto solo testando (vedi report). Fissando qui il tetto,
    # un titolo introvabile nella zona pubblicabile resta "missing" da solo,
    # senza contaminare gli altri.
    end_of_zone = find_heading(lines, TAIL_SENTINEL, body_start + 1)
    if end_of_zone is None:
        end_of_zone = len(lines)
    pos = body_start + 1

    # (riga_intestazione, riga_inizio_corpo, anno, titolo, capitolata)
    located: list[tuple[int, int, str, str, bool]] = []
    missing: list[str] = []
    # posizione in `located` -> titoli non localizzati che cadono nel suo span.
    # La chiave -1 = voci saltate PRIMA della prima opera localizzata: quel
    # testo non finisce in nessuna opera (viene scartato), non contamina.
    swallowed_by: dict[int, list[str]] = {}
    for year, title, chaptered in entries:
        found = find_heading_span(lines, title, pos, end_of_zone)
        if found is None:
            missing.append(title)
            swallowed_by.setdefault(len(located) - 1, []).append(title)
            continue
        head_at, body_at = found
        located.append((head_at, body_at, year, title, chaptered))
        pos = body_at

    # PROMOZIONE LIBRI (vedi docstring modulo, sezione LIBRI vs SERIE).
    # Un contenitore-libro (es. "LA REBELIÓN DE LAS MASAS") nel corpo non ha
    # testo proprio prima della sua prima foglia — quindi il filtro "corpo
    # vuoto" lo scarterebbe e la sua prefazione (prima foglia) inghiottirebbe
    # l'intero libro, perche' i capitoli sono marcatori-figli non localizzati.
    # Lo si riconosce STRUTTURALMENTE: contenitore a corpo vuoto la cui prima
    # foglia e' una PREFAZIONE di apertura (_is_preface) e la cui "run" di
    # foglie consecutive — prefazioni + capitoli (voci `capitolata`) — contiene
    # almeno un capitolo. Le SERIE (EL ESPECTADOR, ENSAYOS DE CRÍTICA) NON
    # scattano: la loro prima foglia e' un articolo, mai una prefazione (anche
    # quando una loro foglia interna e' capitolata, come "Ideas sobre Pío
    # Baroja"). Il libro assorbe contenitore + run in UN'unica opera intitolata
    # al contenitore, con la prefazione come prima parte; il confine finale
    # resta quello gia' calcolato (inizio della foglia successiva alla run).
    # book_head[n] = ultimo indice `located` assorbito dal libro che inizia in n
    book_head: dict[int, int] = {}
    absorbed: set[int] = set()
    n = 0
    while n < len(located):
        body_at = located[n][1]
        end = located[n + 1][0] if n + 1 < len(located) else end_of_zone
        empty = len("\n".join(lines[body_at:end]).strip()) < MIN_BODY_LEN
        if empty and n + 1 < len(located) and _is_preface(located[n + 1][3]):
            run_end = n
            has_chapter = False
            k = n + 1
            while k < len(located):
                _, _, _, k_title, k_chaptered = located[k]
                if _is_preface(k_title) or k_chaptered:
                    has_chapter = has_chapter or k_chaptered
                    run_end = k
                    k += 1
                else:
                    break
            if has_chapter:
                book_head[n] = run_end
                absorbed.update(range(n + 1, run_end + 1))
                n = run_end + 1
                continue
        n += 1

    works: list[Work] = []
    skipped: list[str] = []
    contaminated: list[Contamination] = []
    n = 0
    while n < len(located):
        if n in absorbed:
            n += 1
            continue
        head_at, body_at, year, title, chaptered = located[n]
        if n in book_head:
            run_end = book_head[n]
            end = located[run_end + 1][0] if run_end + 1 < len(located) else end_of_zone
            body = "\n".join(lines[body_at:end]).strip()
            short = _shorten(title)
            works.append(Work(title=short, text=body, kind="work", tomo=label))
            # Contaminazione: raccogli le voci inghiottite da QUALSIASI indice
            # assorbito nel libro (contenitore + run).
            swallowed = [t for i in range(n, run_end + 1)
                         for t in swallowed_by.get(i, [])]
            if swallowed:
                contaminated.append(Contamination(work=short, swallowed=swallowed,
                                                  work_index=len(works) - 1))
            n = run_end + 1
            continue
        end = located[n + 1][0] if n + 1 < len(located) else end_of_zone
        body = "\n".join(lines[body_at:end]).strip()
        if len(body) < MIN_BODY_LEN:
            skipped.append(title)
            n += 1
            continue
        short = _shorten(title)
        works.append(Work(title=short, text=body, kind="work", tomo=label))
        swallowed = swallowed_by.get(n)
        if swallowed:
            contaminated.append(Contamination(work=short, swallowed=swallowed,
                                              work_index=len(works) - 1))
        n += 1

    return TomoExtract(
        label=label, works=works, toc_publishable=len(entries),
        missing=missing, skipped=skipped, contaminated=contaminated,
    )


def extract_all(source: Source) -> ExtractResult:
    blobs = load_tomo_blobs(source)
    return ExtractResult(tomos=[extract_tomo(b) for b in blobs])


def _dedupe(works: list[Work]) -> list[Work]:
    """Titoli duplicati (rubriche ricorrenti su più anni, o stesso titolo in
    tomi diversi): disambigua con l'anno noto nel `tomo` label; se ancora in
    collisione, aggiunge un contatore. Necessario perché write_work scrive
    tutte le opere di un filosofo in un'unica cartella piatta."""
    seen: dict[str, int] = {}
    out: list[Work] = []
    for w in works:
        slug = slugify(w.title)
        if slug not in seen:
            seen[slug] = 1
            out.append(w)
            continue
        seen[slug] += 1
        n = seen[slug]
        new_title = f"{w.title} ({n})"
        while slugify(new_title) in seen:
            n += 1
            new_title = f"{w.title} ({n})"
        seen[slugify(new_title)] = 1
        out.append(Work(title=new_title, text=w.text, kind=w.kind,
                        traduttore=w.traduttore, tomo=w.tomo))
    return out


def run_ortega(source: Source, vault_root: Path) -> ExtractResult:
    result = extract_all(source)
    all_works = _dedupe(result.works)
    i = 0
    for t in result.tomos:
        n = len(t.works)
        t.works = all_works[i: i + n]
        i += n
        # _dedupe puo' aver rinominato l'opera ("titolo (2)"): il report deve
        # nominarla come il file scritto, non col titolo pre-dedupe.
        for c in t.contaminated:
            if 0 <= c.work_index < len(t.works):
                c.work = t.works[c.work_index].title
    for w in all_works:
        write_work(w, source, vault_root)
    return result
