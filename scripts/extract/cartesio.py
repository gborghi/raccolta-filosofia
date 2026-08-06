# scripts/extract/cartesio.py
"""Adapter bespoke per Descartes. Fonte: epub francese, Arvensa Editions 2015
(un solo file .epub, OEBPS/toc.ncx a 2 livelli). Motore condiviso in
arvensa.py; qui solo i dati verificati a mano su QUESTO TOC.

Le 19 opere e le esclusioni sotto sono state verificate leggendo il
contenuto reale dei file html (non dedotte dai soli titoli): "Introduction",
"Avertissement" e "Presentation" sono, a seconda dell'opera, o il testo
autentico di Descartes (voce narrante in prima persona "je") o una nota
editoriale del curatore Arvensa (voce in terza persona / "nous", spesso con
un nome di curatore storico citato: Victor Cousin, Clerselier). Per questo
l'esclusione e' per coppia (opera, titolo-figlio), non per titolo da solo:
lo stesso titolo "Avertissement" e' di Descartes ne LA GEOMETRIE ma del
curatore in PREMIERES PENSEES."""
from __future__ import annotations

from .arvensa import ExtractResult, extract as _arvensa_extract
from .sources import Source

# Le 4 voci di apparato editoriale/pubblicitario che precedono la sezione
# "OEUVRES PHILOSOPHIQUES" nel TOC. Tutte in maiuscolo (altrimenti
# indistinguibili dalle opere solo per case), quindi elencate esplicitamente.
KNOWN_APPARATUS_TITLES: set[str] = {
    "ARVENSA ÉDITIONS",
    "NOTE DE L'ÉDITEUR",
    "CATALOGUE DES ŒUVRES COMPLÈTES NUMÉRIQUES",
    "LISTE DES OEUVRES",
}

# Le 19 opere pubblicabili, nell'ordine del TOC (verificate a mano sul TOC
# reale: 31 voci top-level = 4 apparato + 5 intestazioni di sezione "— X —"
# + 3 apparato d'altro autore (ANNEXES: critica letteraria, elogio,
# biografia — non di Descartes) + queste 19).
EXPECTED_WORKS: list[str] = [
    "DISCOURS DE LA MÉTHODE",
    "MÉDITATIONS MÉTAPHYSIQUES",
    "OBJECTIONS AUX MÉDITATIONS",
    "LES PRINCIPES DE LA PHILOSOPHIE",
    "LES PASSIONS DE L’ÂME",
    "LE MONDE OU LE TRAITÉ DE LA LUMIÈRE",
    "TRAITÉ DE L’HOMME",
    "DE LA FORMATION DU FŒTUS",
    "LA DIOPTRIQUE",
    "LES MÉTÉORES",
    "TRAITÉ DE LA GÉOMÉTRIE",
    "TRAITÉ DE LA MÉCANIQUE",
    "ABRÉGÉ DE LA MUSIQUE",
    "LETTRES",
    "LETTRE DE RENÉ DESCARTES A GISBERT VOET",
    "RÈGLES POUR LA DIRECTION DE L’ESPRIT",
    "RECHERCHE DE LA VÉRITÉ PAR LES LUMIÈRES NATURELLES",
    "PREMIÈRES PENSÉES SUR LA GÉNÉRATION DES ANIMAUX ET LES SAVEURS",
    "EXTRAIT DES MANUSCRITS DE RENÉ DESCARTES",
]

# Voci-figlie che sono apparato del curatore SOLO in questa opera (verificato
# leggendo il testo: voce editoriale in terza persona/"nous", o nota firmata
# da un curatore storico nominato). "Table des matières" e' sempre esclusa a
# monte (universal_exclude_children in arvensa.py), non serve ripeterla qui.
EXCLUDE_CHILD_PAIRS: set[tuple[str, str]] = {
    # Le Monde / Traite de l'Homme: "Introduction" cita Clerselier come
    # "le premier editeur" in terza persona -> non e' di Descartes.
    ("LE MONDE OU LE TRAITÉ DE LA LUMIÈRE", "Introduction"),
    ("TRAITÉ DE L’HOMME", "Introduction"),
    # Geometrie: nota firmata esplicitamente "Note de Victor Cousin".
    ("TRAITÉ DE LA GÉOMÉTRIE", "Note de Victor Cousin"),
    # Lettres: "Avant-propos" e' editoriale ("nous avons substitue... l'ordre
    # chronologique"); "Appendice de la correspondance" e' un glossario
    # biografico moderno dei corrispondenti; "Planches des illustrations" e'
    # solo un rimando a tavole illustrative, nessun testo.
    ("LETTRES", "Avant-propos"),
    ("LETTRES", "Appendice de la correspondance"),
    ("LETTRES", "Planches des illustrations"),
    # Principes: idem, solo rimando a tavole illustrative.
    ("LES PRINCIPES DE LA PHILOSOPHIE", "Planches des illustrations"),
    # Regles / Recherche de la Verite: "Presentation" cita Victor Cousin in
    # terza persona come voce editoriale introduttiva.
    ("RÈGLES POUR LA DIRECTION DE L’ESPRIT", "Présentation"),
    ("RECHERCHE DE LA VÉRITÉ PAR LES LUMIÈRES NATURELLES", "Présentation"),
    # Passions: le "Lettre I/II à M. Descartes" sono lettere scritte A
    # Descartes (da Elisabeth di Boemia), non da lui; le "Reponse" restano
    # (sono di Descartes) e non sono in questo insieme.
    ("LES PASSIONS DE L’ÂME", "Lettre I à M. Descartes"),
    ("LES PASSIONS DE L’ÂME", "Lettre II à M. Descartes"),
    # Premieres Pensees: "Avertissement" e' un avviso editoriale moderno che
    # discute l'autenticita' del frammento ("nous jugeons utile de
    # reproduire... nous rejetons l'authenticite de ce fragment").
    ("PREMIÈRES PENSÉES SUR LA GÉNÉRATION DES ANIMAUX ET LES SAVEURS", "Avertissement"),
}


def extract(source: Source) -> ExtractResult:
    return _arvensa_extract(
        source,
        expected_works=EXPECTED_WORKS,
        known_apparatus_titles=KNOWN_APPARATUS_TITLES,
        exclude_child_pairs=EXCLUDE_CHILD_PAIRS,
    )
