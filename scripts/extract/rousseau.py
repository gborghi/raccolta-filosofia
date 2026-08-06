# scripts/extract/rousseau.py
"""Adapter bespoke per Rousseau (Arvensa Editions). Analogo a delphi.py, ma
la sorgente non e' un Delphi Classics: ogni titolo di "LISTE DES TITRES" ha
una propria "cascata" di apertura (titolo/sottotitolo/"* * *"/anno/autore/
sezione/"* * *") seguita da un indice locale dei capitoli e da intestazioni
di navigazione ("breadcrumb") che si ripetono prima di OGNI capitolo/
lettera interna. Nessuna di queste due cose esiste in Delphi: la logica di
localizzazione e ripulitura e' quindi scritta da zero (vedi commenti nelle
singole funzioni), non riusa delphi_body.py.

Verificato sull'intero testo concatenato (non su un campione): 99/102 voci
di TOC localizzate; le 3 mancanti sono le 2 voci editoriali di apertura
(ARVENSA EDITIONS, NOTE DE L'EDITEUR - apparato puro, mai pubblicato
comunque) e "OBSERVATIONS sur les retranchements..." che non ha una propria
pagina dedicata nel testo (risulta assorbita nel materiale intorno a
JULIE) e viene quindi segnalata come "missing" invece di essere pubblicata
a caso.

CONFINE DI COPYRIGHT / APPARATO EDITORIALE (M2, passata di lettura manuale):
_extract_body() sopra rimuove solo l'apparato STRUTTURALE Arvensa comune a
tutte le 86 opere (cascata di apertura, indice locale, breadcrumb ripetuti).
Non rimuove l'apparato CURATORIALE ottocentesco (introduzioni firmate
Musset-Pathay/Petitain, biografie in terza persona, lettere altrui
riprodotte prima della risposta di Rousseau): una lettura riga per riga
delle 86 opere estratte ha verificato che 34 di esse iniziano cosi', non
con la voce di Rousseau.

Il confine e' quindi applicato con lo STESSO contratto fail-closed di
delphi.py, riusando strip_to_start() di delphi_body.py (funzione generica,
non specifica a Delphi: opera su una stringa di corpo e una first_line,
esattamente il contratto che serve qui) su data/work_starts.json["rousseau"]:
- chiave di lookup = out_title (il titolo finale dell'opera, identico al
  frontmatter "title" scritto su disco, non il titolo grezzo del TOC che a
  volte porta "(Annexe)" o suffissi di data);
- "first_line" assente (chiave o intera entry) = non lo sappiamo = unmarked,
  MAI pubblicata a caso;
- "first_line": "" scritta a mano = verificato, il testo di Rousseau comincia
  già dove si ferma _extract_body(), nessun taglio ulteriore;
- "first_line": "<riga esatta>" = lì comincia il testo vero di Rousseau,
  tutto ciò che precede (compresa una eventuale prefazione ottocentesca) è
  apparato e va tagliato.

Verificato caso per caso (non per euristica): una prefazione/avvertissement
è stata trattata come testo di Rousseau (e quindi NON tagliata) solo se
scritta in prima persona da lui stesso — es. la Préface di JULIE
("Il faut des spectacles...") e quella di ÉMILE ("Ce recueil de réflexions
et d'observations...") sono autentiche e restano; l'"Avis" firmato "M.P."
davanti a LETTRE À D'ALEMBERT SUR LES SPECTACLES o la nota firmata
"M. Musset-Pathay" davanti a ORAISON FUNÈBRE DU DUC D'ORLÉANS sono apparato
e vengono tagliati. Dettagli caso per caso nelle "note" di ogni entry.

Effetto collaterale scoperto durante la lettura (non un problema di
apparato, segnalato qui perché usa lo stesso contratto fail-closed): i corpi
attualmente estratti per "Correspondance I/II/III/IV" sono vuoti di lettere
vere (solo l'indice per anno, un bug nel confine di fine-slab per
kind="letters", non ancora risolto) — non hanno una entry in
work_starts.json e quindi restano "unmarked" invece di pubblicare uno stub.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .common import Work
from .delphi_body import strip_to_start
from .rousseau_toc import TocEntry, body_search_start, parse_toc
from .sources import Source

# ---------------------------------------------------------------------------
# Normalizzazione titoli: il corpo diverge dalla "LISTE DES TITRES" in modi
# sistematici, verificati caso per caso (non ipotizzati):
#   - "(Annexe)" non compare mai nel corpo (es. "RECUEIL D'ESTAMPES (Annexe)"
#     -> corpo "RECUEIL D'ESTAMPES").
#   - Le 5 parti di CORRESPONDANCE portano un intervallo di date dopo un
#     trattino nel TOC ma a volte no nel corpo: si prova prima il titolo
#     intero, poi senza suffisso.
#   - Alcune "LETTRE(S) A X" nel corpo perdono la parola iniziale
#     "LETTRE(S)" (es. "LETTRE A MONSIEUR PHILOPOLIS" -> corpo "A MONSIEUR
#     PHILOPOLIS").
#   - La virgola e' incostante ("DU CONTRAT SOCIAL ou..." nel TOC vs
#     "DU CONTRAT SOCIAL, ou..." nel corpo): il confronto ignora le virgole.
# ---------------------------------------------------------------------------
ANNEXE_RE = re.compile(r'\s*\(Annexe\)\s*$')
DASH_SUFFIX_RE = re.compile(r'\s+[–—]\s+.*$')
LEADING_LETTRE_RE = re.compile(r'^LETTRES?\s+', re.IGNORECASE)


def _title_variants(title: str) -> list[str]:
    out = []
    t0 = ANNEXE_RE.sub('', title).strip()
    out.append(t0)
    t1 = DASH_SUFFIX_RE.sub('', t0).strip()
    if t1 != t0:
        out.append(t1)
    for base in (t0, t1):
        m = LEADING_LETTRE_RE.match(base)
        if m:
            cand = base[m.end():].strip()
            if cand and cand not in out:
                out.append(cand)
    return out


def _norm(s: str) -> str:
    return s.replace(",", "").strip()


def _next_nonblank(lines: list[str], i: int, window: int = 8) -> str:
    for j in range(i + 1, min(i + 1 + window, len(lines))):
        s = lines[j].strip()
        if s:
            return s
    return ""


def _has_cascade(lines: list[str], i: int, lookahead_nonblank: int = 3) -> bool:
    """La cascata di apertura vera ha "* * *" entro le prime 1-2 righe non
    vuote dopo il titolo. Una finestra larga cattura per errore le voci
    nude della "Liste generale des titres" ripetuta prima di ogni opera
    (che raggiunge comunque un "* * *" piu' avanti, ma non a ridosso):
    verificato che allargare la finestra fa localizzare JULIE 4 righe prima
    del vero inizio, dentro l'elenco ripetuto anziche' nella sua cascata."""
    nb: list[str] = []
    for j in range(i + 1, len(lines)):
        s = lines[j].strip()
        if s:
            nb.append(s)
        if len(nb) >= lookahead_nonblank:
            break
    return "* * *" in nb


def _find_entry(
    lines: list[str], title: str, start_pos: int, all_titles_norm: set[str]
) -> tuple[int, str, str] | None:
    """Localizza l'occorrenza di `title` che apre il vero contenuto
    dell'opera, cercando in ordine da `start_pos` (avanza monotono fra le
    voci del TOC, come find_body_line in delphi_body.py).

    Tier "strong": titolo + cascata "* * *" confermata.
    Tier "weak" (fallback, usato per Correspondance/Cronologia che non
    hanno cascata "* * *"): prima occorrenza il cui successore non e'
    anch'esso un titolo noto (altrimenti e' solo una voce dentro un
    elenco, non un header di corpo)."""
    candidates = _title_variants(title)
    best: tuple[int, str, str] | None = None
    for v in candidates:
        i = start_pos
        while i < len(lines):
            idx = None
            for k in range(i, len(lines)):
                if _norm(lines[k].strip()) == _norm(v):
                    idx = k
                    break
            if idx is None:
                break
            if _has_cascade(lines, idx):
                if best is None or idx < best[0]:
                    best = (idx, v, "strong")
                break
            i = idx + 1
    if best:
        return best

    v = candidates[0]
    i = start_pos
    while i < len(lines):
        if _norm(lines[i].strip()) == _norm(v):
            succ = _next_nonblank(lines, i)
            if _norm(succ) not in all_titles_norm:
                return (i, v, "weak")
        i += 1
    return None


# ---------------------------------------------------------------------------
# Pulitura del corpo: ogni opera e' preceduta da una cascata di apertura e
# da un indice locale dei capitoli, e ogni capitolo/lettera INTERNO e'
# preceduto a sua volta da un blocco di navigazione ("breadcrumb") che
# ripete titolo/sezione/link di indice. Nessuno di questi e' testo di
# Rousseau: vanno tolti entrambi.
# ---------------------------------------------------------------------------
BREADCRUMB_ANCHOR = "J. J. Rousseau : Oeuvres complètes"


def _is_nav_marker(s: str) -> bool:
    # "Table des matières" compare anche come "Table des matières du
    # titre" in alcune opere (es. LES CONFESSIONS): confronto per prefisso.
    return s == "Liste générale des titres" or s.startswith("Table des matières")


def _strip_breadcrumbs(seg_lines: list[str]) -> list[str]:
    """Rimuove ogni blocco che inizia con BREADCRUMB_ANCHOR fino all'ULTIMO
    fra i due marker di navigazione incontrato entro le prime righe non
    vuote successive: le due varianti osservate nel testo hanno ordine
    diverso ("Table des matieres" a volte e' l'ultimo elemento del blocco,
    a volte il primo), quindi si cerca l'ultimo dei due, non il primo."""
    out: list[str] = []
    i, n = 0, len(seg_lines)
    while i < n:
        if seg_lines[i].strip() == BREADCRUMB_ANCHOR:
            j = i + 1
            nb_idx: list[int] = []
            cnt = 0
            while j < n and cnt < 16:
                if seg_lines[j].strip():
                    nb_idx.append(j)
                    cnt += 1
                j += 1
            end = None
            for k in nb_idx:
                if _is_nav_marker(seg_lines[k].strip()):
                    end = k
            if end is not None:
                i = end + 1
                continue
        out.append(seg_lines[i])
        i += 1
    return out


PROSE_MIN_LEN = 120
SHORT_LINE_LEN = 70
RUN_MIN_ENTRIES = 6
STABLE_LOOKAHEAD = 6
STABLE_LONG_LEN = 100


def _find_content_start(stripped: list[str]) -> int:
    """`stripped` e' gia' ripulito dai breadcrumb ripetuti. Resta: cascata
    di apertura, indice locale dei capitoli (righe corte), ed eventuali
    note editoriali Arvensa (a volte corte, a volte un paragrafo lungo
    prima dell'indice stesso - verificato su LETTRES ECRITES DE LA
    MONTAGNE). Si cercano tutti i "cluster" di righe corte consecutive
    (>=6 voci di lunghezza <=70: intestazioni di capitolo/lettera, mai
    prosa) e si prende il PRIMO cluster seguito da prosa STABILE (la
    maggioranza delle righe successive e' lunga).

    Perche' il primo e non l'ultimo cluster stabile: un dialogo con
    battute brevi DENTRO il corpo vero (es. "R." / "N." nella Seconde
    Preface di Julie) crea un cluster short-line tardivo che non deve far
    scartare un cluster precedente gia' valido - verificato: prendere
    l'ultimo cluster porta a saltare "Avis"/"Preface"/"Avertissement" di
    Julie e atterrare dentro quel dialogo, perdendo testo autentico.
    """
    nb = [(i, l.strip()) for i, l in enumerate(stripped) if l.strip()]
    window = nb[:600]
    runs: list[int] = []  # posizioni-token (indice in `window`) dopo ogni cluster
    i = 0
    while i < len(window):
        if len(window[i][1]) <= SHORT_LINE_LEN:
            j = i
            while j < len(window) and len(window[j][1]) <= SHORT_LINE_LEN:
                j += 1
            if j - i >= RUN_MIN_ENTRIES:
                runs.append(j)
            i = j
        else:
            i += 1

    chosen = None
    for r in runs:
        followers = [window[k][1] for k in range(r, min(r + STABLE_LOOKAHEAD, len(window)))]
        if not followers:
            continue
        long_count = sum(1 for f in followers if len(f) >= STABLE_LONG_LEN)
        if long_count >= max(1, len(followers) - 1):
            chosen = r
            break
    if chosen is None and runs:
        # Nessun cluster e' seguito da prosa stabile (es. un'opera teatrale
        # breve dove il primo paragrafo e' seguito subito da un elenco di
        # "Personnages"/"Scene", che forma un secondo cluster tardivo -
        # verificato su "COURTS FRAGMENTS DE LUCRECE" e "LE DEVIN DU
        # VILLAGE"): prendere l'ULTIMO cluster in questo caso atterra oltre
        # il vero inizio. Il PRIMO cluster e' quasi sempre la cascata di
        # apertura + indice locale, il punto piu' sicuro da cui ripartire.
        chosen = runs[0]

    anchor = window[chosen][0] if chosen is not None and chosen < len(window) else 0

    idx = None
    for k in range(anchor, len(stripped)):
        if len(stripped[k].strip()) >= PROSE_MIN_LEN:
            idx = k
            break
    if idx is None:
        # Mai trovata una riga di prosa (soglia PROSE_MIN_LEN): tipico dei
        # testi in versi (es. "CHOIX DE ROMANCES", righe di canzone sempre
        # corte). Non e' un risultato affidabile: il chiamante applica una
        # rete di sicurezza aggiuntiva solo in questo caso.
        return anchor, False
    j = idx - 1
    while j > anchor and not stripped[j].strip():
        j -= 1
    return max(j, anchor), True


RESIDUAL_MARKERS = ("www.arvensa.com", "Liste générale des titres")


def _skip_residual_front_matter(stripped: list[str], cstart: int, window: int = 60) -> int:
    """Rete di sicurezza usata SOLO quando _find_content_start non ha mai
    trovato una riga di prosa (soglia PROSE_MIN_LEN) - verificato su
    "CHOIX DE ROMANCES": e' una raccolta di testi di canzoni (versi brevi,
    mai >=120 caratteri), quindi l'euristica principale non scavalca mai la
    cascata di apertura e ritorna l'inizio dello slab. In quel caso, se il
    blocco di contatto Arvensa (chiuso da "www.arvensa.com") o il link
    "Liste generale des titres" compaiono entro le prime righe, si salta
    oltre l'ultima occorrenza trovata: sono testo editoriale certo.

    NON va applicata quando _find_content_start e' gia' andato a buon fine
    (confident=True): verificato che farlo comunque, con una finestra
    larga, intercetta occorrenze incidentali di questi marker DENTRO il
    corpo vero (es. note a pie' di pagina) e tronca opere corte gia'
    correttamente estratte (es. "PLANCHES SUR LA BOTANIQUE")."""
    last = None
    for k in range(cstart, min(cstart + window, len(stripped))):
        if stripped[k].strip() in RESIDUAL_MARKERS:
            last = k
    return last + 1 if last is not None else cstart


def _extract_body(lines: list[str], idx_start: int, idx_end: int) -> str:
    slab = lines[idx_start:idx_end]
    stripped = _strip_breadcrumbs(slab)
    cstart, confident = _find_content_start(stripped)
    if not confident:
        cstart = _skip_residual_front_matter(stripped, cstart)
    return "\n".join(stripped[cstart:]).strip()


# Le 5 parti di Correspondance hanno nel TOC un titolo lungo con
# l'intervallo di date ("PREMIERE PARTIE - Du 1er janvier 1732 au 1er
# janvier 1758"): titoli brevi qui per lo slug (vincolo MAX_PATH) e per
# leggibilita' nel vault.
CORRESPONDANCE_TITLES = [
    "Correspondance I (1732-1758)",
    "Correspondance II (1758-1763)",
    "Correspondance III (1763-1766)",
    "Correspondance IV (1766-1768)",
    "Correspondance V (1768-1778)",
]

MIN_BODY_LEN = 50


@dataclass
class ExtractResult:
    works: list[Work] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)   # work/letters mai localizzati
    unmarked: list[str] = field(default_factory=list)   # localizzati ma corpo vuoto/troppo corto
    skipped: list[str] = field(default_factory=list)    # apparatus localizzato, escluso di proposito


def extract(text: str, source: Source, starts: dict | None = None) -> ExtractResult:
    starts = starts or {}
    entries: list[TocEntry] = parse_toc(text)
    lines = text.split("\n")

    all_titles_norm: set[str] = set()
    for e in entries:
        for v in _title_variants(e.title):
            all_titles_norm.add(_norm(v))

    pos = body_search_start(text)
    located: list[tuple[int, TocEntry]] = []
    missing: list[str] = []
    for e in entries:
        res = _find_entry(lines, e.title, pos, all_titles_norm)
        if res is None:
            if e.kind in ("work", "letters"):
                missing.append(e.title)
            continue
        idx, _matched, _tier = res
        located.append((idx, e))
        pos = idx + 1

    works: list[Work] = []
    unmarked: list[str] = []
    skipped: list[str] = []
    used_titles: dict[str, int] = {}
    letters_seen = 0

    for n, (idx, entry) in enumerate(located):
        if entry.kind == "apparatus":
            skipped.append(entry.title)
            continue

        idx_end = located[n + 1][0] if n + 1 < len(located) else len(lines)
        body = _extract_body(lines, idx, idx_end)

        # out_title va calcolato PRIMA di sapere se l'opera sara' pubblicata:
        # per kind="letters" la mappatura su CORRESPONDANCE_TITLES e'
        # posizionale (segue l'ordine del TOC, I..V), quindi letters_seen
        # deve avanzare per OGNI voce "letters" incontrata, pubblicata o no.
        # Farlo avanzare solo sui successi (come used_titles sotto)
        # disallineerebbe la mappa se una delle prime parti finisse
        # unmarked: la parte successiva erediterebbe per errore il titolo
        # di quella saltata.
        if entry.kind == "letters":
            out_title = CORRESPONDANCE_TITLES[letters_seen] if letters_seen < len(CORRESPONDANCE_TITLES) else entry.title
            letters_seen += 1
        else:
            out_title = ANNEXE_RE.sub('', entry.title).strip()

        # data/work_starts.json["rousseau"] dice dove finisce l'apparato
        # curatoriale ottocentesco (Musset-Pathay, Petitain, biografie in
        # terza persona...) e comincia il testo vero di Rousseau. Stesso
        # contratto fail-closed di delphi.py: la chiave "first_line" deve
        # essere presente esplicitamente. Solo "first_line": "" scritta a
        # mano significa "verificato: _extract_body() si ferma già dove
        # comincia Rousseau, nessun taglio ulteriore". Assente (chiave o
        # intera entry) = non lo sappiamo: si segnala, non si pubblica a
        # caso.
        info = starts.get(out_title)
        if info is None or "first_line" not in info:
            unmarked.append(entry.title)
            continue
        clean, found = strip_to_start(body, info["first_line"])
        # Vuoto/non trovato dopo il taglio e' un fallimento pari a "marker
        # non trovato": non si scarta in silenzio (stesso criterio di
        # delphi.py). MIN_BODY_LEN resta la soglia di guardia anche qui
        # (es. i corpi-stub di Correspondance II/III/IV, che pero' restano
        # gia' unmarked prima di arrivare qui perche' assenti dal json).
        if not found or not clean or len(clean) < MIN_BODY_LEN:
            unmarked.append(entry.title)
            continue

        if out_title in used_titles:
            used_titles[out_title] += 1
            out_title = f"{out_title} ({used_titles[out_title]})"
        else:
            used_titles[out_title] = 1

        works.append(Work(title=out_title, text=clean, kind=entry.kind,
                          traduttore=info.get("traduttore")))

    return ExtractResult(works=works, missing=missing, unmarked=unmarked, skipped=skipped)
