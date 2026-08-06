# scripts/extract/rousseau_toc.py
"""Parser del "LISTE DES TITRES" di Arvensa Editions (Rousseau, Oeuvres
completes - 93 titres).

STRUTTURA TROVATA (verificata sull'intero testo concatenato part1..7, non
su un campione):

  - Il documento apre con un blocco editoriale Arvensa (copertina, "NOTE DE
    L'EDITEUR", "PREFACE DE LOUIS-GUILLAUME DESCHARD" - una prefazione di
    un curatore moderno, non di Rousseau), poi la riga "LISTE DES TITRES":
    l'indice generale dell'intera raccolta.

  - Sotto "LISTE DES TITRES", le sezioni sono marcate da una riga fra
    trattini: "– TITOLO –" o "— TITOLO —" (en/em dash, spaziatura variabile).
    Sezioni trovate, in ordine: OEUVRE LITTERAIRE, OEUVRE PHILOSOPHIQUE ET
    POLITIQUE, BOTANIQUE, MELANGES OU LITTERATURE VARIEE, ECRITS SUR LA
    MUSIQUE, MEMOIRES, CORRESPONDANCE, ANNEXES.

  - Dentro "MELANGES OU LITTERATURE VARIEE" ci sono 3 sotto-etichette SENZA
    trattini (MELANGES EN PROSE, PIECES DE THEATRE, MELANGES EN VERS): sono
    semplici raggruppamenti tipografici, non producono un'opera propria e
    non hanno un proprio "titolo" nel corpo.

  - Ogni voce puo' portare il suffisso letterale " (Annexe)": e' Arvensa
    stessa a marcare cosi' il materiale accessorio (verificato aprendo i
    corpi: "DU GOUVERNEMENT DE GENEVE (Annexe)" e' firmato "Jean le Rond
    D'ALEMBERT", non Rousseau; "ARRET DE LA COUR DE PARLEMENT (Annexe)" e'
    un atto giudiziario; "EXTRAIT DES REGISTRES..." un verbale ufficiale).
    Nel corpo il suffisso "(Annexe)" NON compare: va tolto per la ricerca.

  - La sezione "— ANNEXES —" finale e' interamente apparato editoriale
    postumo: BIOGRAPHIE, CHRONOLOGIE..., PRECIS DES CIRCONSTANCES...,
    ESSAI SUR LA VIE ET LE CARACTERE... (biografie/cronologie, non testi di
    Rousseau).

  - La sezione "— CORRESPONDANCE —" elenca 5 "PARTIE" (blocchi di
    corrispondenza autentica di Rousseau, organizzati per anno): kind
    "letters", distinto da "work" perche' non sono opere composte ma
    raccolte epistolari.

CLASSIFICAZIONE kind (decisione esplicita, si veda il report):
  - "apparatus": blocco pre-sezione (ARVENSA EDITIONS, NOTE DE L'EDITEUR,
    PREFACE DE LOUIS-GUILLAUME DESCHARD), intera sezione ANNEXES, e ogni
    voce con suffisso "(Annexe)" ovunque compaia. MAI pubblicato.
  - "letters": le 5 parti di CORRESPONDANCE.
  - "work": tutto il resto (87 voci: essais, discours, lettere pubblicate,
    teatro, musica, memorie...). Arvensa stessa le elenca come "titres"
    paritari, senza distinguere ulteriormente opere maggiori da lettere
    polemiche minori (es. "LETTRE A M. GRIMM" accanto a "DU CONTRAT
    SOCIAL"): non essendoci un segnale strutturale affidabile per separarle
    senza leggere ogni testo, si pubblicano tutte come "work".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SECTION_RE = re.compile(r'^[–—]\s*(.+?)\s*[–—]$')

# Le tre voci di apertura (prima della prima sezione con trattini): sono
# l'apparato Arvensa stesso, non un "titolo" della raccolta.
PRE_SECTION_APPARATUS = frozenset({
    "ARVENSA ÉDITIONS", "NOTE DE L’ÉDITEUR", "PRÉFACE DE LOUIS-GUILLAUME DESCHARD",
})

# Sotto-etichette senza trattini dentro MELANGES OU LITTERATURE VARIEE:
# raggruppamenti, non opere.
SUBSECTION_LABELS = frozenset({
    "MÉLANGES EN PROSE", "PIÈCES DE THÉÂTRE", "MÉLANGES EN VERS",
})

ANNEXES_SECTION = "ANNEXES"
CORRESPONDANCE_SECTION = "CORRESPONDANCE"

TOC_START_MARK = "LISTE DES TITRES"
PREFACE_MARK = "PRÉFACE DE LOUIS-GUILLAUME DESCHARD"


@dataclass(frozen=True)
class TocEntry:
    section: str | None   # None per le 3 voci pre-sezione
    title: str             # come appare in "LISTE DES TITRES" (con eventuale "(Annexe)")
    kind: str               # "work" | "letters" | "apparatus"


def body_search_start(text: str) -> int:
    """Indice di riga da cui iniziare a cercare gli header di corpo: la
    SECONDA occorrenza di PREFACE_MARK (la prima e' la voce nella
    "LISTE DES TITRES", identico confine usato da parse_toc per la fine
    del TOC). Se non trovato, ricerca dall'inizio (fail-open solo qui:
    parse_toc avrebbe gia' restituito lista vuota in quel caso)."""
    lines = text.split("\n")
    try:
        first_pref = next(i for i, l in enumerate(lines) if l.strip() == PREFACE_MARK)
        return next(
            i for i, l in enumerate(lines[first_pref + 1:], start=first_pref + 1)
            if l.strip() == PREFACE_MARK
        )
    except StopIteration:
        return 0


def parse_toc(text: str) -> list[TocEntry]:
    """Estrae la "LISTE DES TITRES": dalla riga omonima fino alla SECONDA
    occorrenza di "PREFACE DE LOUIS-GUILLAUME DESCHARD" (la prima e' la
    voce d'indice, la seconda apre il corpo reale della prefazione: e' il
    confine naturale di fine-TOC, analogo a TOC_END in delphi_toc.py)."""
    lines = text.split("\n")
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == TOC_START_MARK)
    except StopIteration:
        return []
    try:
        first_pref = next(i for i, l in enumerate(lines) if l.strip() == PREFACE_MARK)
        second_pref = next(
            i for i, l in enumerate(lines[first_pref + 1:], start=first_pref + 1)
            if l.strip() == PREFACE_MARK
        )
    except StopIteration:
        return []

    toc_lines = [l.strip() for l in lines[start + 1:second_pref] if l.strip()]

    entries: list[TocEntry] = []
    section: str | None = None
    for l in toc_lines:
        m = SECTION_RE.match(l)
        if m:
            section = m.group(1)
            continue
        if l in PRE_SECTION_APPARATUS:
            entries.append(TocEntry(None, l, "apparatus"))
            continue
        if l in SUBSECTION_LABELS:
            continue
        if section is None:
            continue
        if section == ANNEXES_SECTION:
            kind = "apparatus"
        elif section == CORRESPONDANCE_SECTION:
            kind = "letters"
        elif l.endswith("(Annexe)"):
            kind = "apparatus"
        else:
            kind = "work"
        entries.append(TocEntry(section, l, kind))
    return entries
