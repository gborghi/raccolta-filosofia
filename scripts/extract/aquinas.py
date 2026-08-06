# scripts/extract/aquinas.py
"""Adapter bespoce per Tommaso d'Aquino, Summa Theologica. Fonte: UN SOLO
PDF con testo estraibile (non scansione), 4201 pagine, edizione CCEL
(Christian Classics Ethereal Library) - www.ccel.org/ccel/aquinas/summa.html.

PROVENIENZA (verificata leggendo il PDF, non assunta):
- pagina PDF indice 1 ("About Summa Theologica"): Title:
  http://www.ccel.org/ccel/aquinas/summa.html · Author(s): Thomas Aquinas,
  Saint (1225?-1274) · Rights: Public Domain.
- pagina PDF indice 152 (titolo interno del corpo, prima di "FIRST PART"):
    ST. THOMAS AQUINAS / SUMMA THEOLOGICA
    SUMMA THEOLOGICA (Benziger Bros. edition, 1947)
    Translated by Fathers of the English Dominican Province
    Acknowledgement: ... Sandra K. Perry, Perrysburg, Ohio.
  Quindi: traduzione dei Fathers of the English Dominican Province
  (pubblicata a scaglioni 1911-1925 dai Benziger Brothers; la ristampa
  Benziger 1947 citata qui e' la stessa traduzione, non una nuova versione
  protetta - stesso principio gia' usato per Descartes/Nietzsche in questo
  progetto: il boilerplate di un'edizione successiva non protegge un testo
  gia' pubblico dominio). pd_year=1925 = fine pubblicazione a scaglioni
  dell'edizione originale (tutti i volumi pre-1928, oggi abbondantemente PD
  US); il PDF stesso dichiara "Rights: Public Domain" senza condizioni.
- metadata PDF: Title="Summa Theologica", Author="Saint Thomas Aquinas",
  Creator="XEP 3.7.3 Client Academic" (il motore di render usato da CCEL
  per i propri PDF), creationDate 2004 - coerente con un export CCEL.

STRUTTURA VERA (verificata leggendo TUTTE le Parti, non un campione):
  Parte (FIRST PART / FIRST PART OF THE SECOND PART / SECOND PART OF THE
  SECOND PART / THIRD PART / SUPPLEMENT)
    -> Trattato ("TREATISE ON ..." in maiuscolo, con range di Questioni fra
       parentesi: "(QQ[2]-26)" o singolo "(Q[1])")
      -> Questione (titolo in maiuscolo + "(N ARTICLES)" in lettere, es.
         "THE EXISTENCE OF GOD (THREE ARTICLES)" - MAI preceduta dalla
         dicitura "Question. N" nel corpo: quella dicitura esiste SOLO nel
         Table of Contents, pagine 2-151)
        -> Articolo (la domanda stessa, es. "Whether God exists?", seguita
           da "Objection 1:" ... "On the contrary" ... "I answer that,"
           ... "Reply to Objection N:" - MAI preceduto da "Article. N" nel
           corpo, di nuovo solo nel TOC)
  Il TOC (pagine indice 2-151, numerazione romana i..cli/clii in calce) e'
  tutto apparato (indice, "About This Book", pagina del titolo) e va
  escluso in blocco. Il corpo vero comincia a pagina indice 153
  ("FIRST PART (FP: QQ 1-119)") e finisce a pagina indice 4183 (fine
  dell'Appendice "TWO ARTICLES ON PURGATORY"): da pagina 4184 in poi c'e'
  solo l'Index of Scripture References (tabelle riferimento-pagina per
  centinaia di pagine, puro apparato, mai testo di Tommaso) fino a fine
  file (pagina 4200).

  Ogni pagina del corpo termina con un piede di pagina ricorrente:
  "<numero pagina interno>\nSaint Thomas Aquinas\nSumma Theologica\n" -
  nessuna intestazione in cima pagina. Va rimosso ovunque, altrimenti il
  numero e il nome finiscono in mezzo alle frasi (verificato su decine di
  pagine campione in tutte le Parti, pattern identico).

GRANULARITA': un file per TRATTATO (non per Parte, non un unico blob da
4201 pagine). Motivazione: il Trattato e' l'unita' che la stessa edizione
dichiara esplicitamente con un'intestazione dedicata e un range di
Questioni proprio; alcune Parti (es. Second Part of the Second Part) ne
contengono diversi di dimensione molto diversa, e trattarle come un unico
file le renderebbe illeggibili nel viewer SPA e romperebbero l'atomizzatore
a valle. Il testo di ogni file conserva le intestazioni di Trattato,
Questione e Articolo cosi' come appaiono nel PDF (nessuna e' stata
inventata o rinumerata).

31 trattati totali, verificati leggendo l'intestazione reale di ognuno
sul PDF (non dedotti dal solo TOC, che elenca "Treatise on..." solo per
alcuni e omette le suddivisioni non etichettate come tali nel TOC):
- FIRST PART: 10 trattati (di cui gli ultimi due, "Distinction of Things
  In General" Q[47] e "Distinction of Good And Evil" QQ[48]-49, sono gia'
  sotto-trattati esplicitamente etichettati dentro il trattato madre "The
  Creation" QQ[44]-49 - la stessa edizione li stacca con un'intestazione
  propria, quindi diventano file propri).
- FIRST PART OF THE SECOND PART: 8 trattati (il trattato TOC "Habits in
  Particular (QQ[55]-89)" e' diviso in corpo in due blocchi con
  intestazione propria: "GOOD HABITS, i.e. VIRTUES (QQ[55]-70)" e "EVIL
  HABITS, i.e. VICES AND SINS (QQ[71]-89)" - qui diventano due file,
  "Treatise on the Virtues" e "Treatise on Vice and Sin").
- SECOND PART OF THE SECOND PART: 5 trattati (il trattato TOC "Cardinal
  Virtues (QQ[47]-170)" e' diviso in corpo fra il blocco iniziale
  Prudenza+Giustizia e un'intestazione propria "TREATISE ON FORTITUDE AND
  TEMPERANCE (QQ[123]-170)" - due file). NOTA: dentro questa sezione
  esistono anche intestazioni corte con singola Questione fra parentesi
  quadre, es. "VICES OPPOSED TO DISTRIBUTIVE JUSTICE (Q[63])",
  "SERVICE BY PROMISE (Q[88])", "CONFIRMATION (Q[72])" nel Terzo: NON sono
  confini di trattato, sono semplicemente titoli di Questione che (a
  differenza della norma "(N ARTICLES)" in lettere) citano la propria
  Questione fra parentesi quadre - verificato leggendo il testo intorno:
  in ognuno dei tre casi il paragrafo prosegue dritto con Obiezioni di
  quella singola Questione, non introduce un nuovo range di Questioni.
  Il discriminante affidabile usato per i confini di trattato in questo
  adapter e' "QQ[" (plurale, range) oppure un'intestazione preceduta da
  "TREATISE ON"/"TREATISE OF" - mai un singolo "(Q[N])" isolato.
- THIRD PART: 2 trattati (nessuna suddivisione ulteriore trovata:
  "Incarnation" QQ[1]-59 e "Sacraments" QQ[60]-90 restano un file ciascuno,
  431 e 303 pagine PDF rispettivamente - verificato che non esistono altre
  intestazioni "TREATISE ON"/bare-noun con range QQ dentro questi
  intervalli, es. Battesimo ed Eucaristia NON hanno intestazione propria,
  solo Questioni ordinarie "OF ...").
- SUPPLEMENT: 6 trattati. Il Supplement (compilato da Fra Rainaldo da
  Piperno dal commento di Tommaso alle Sentenze, dopo la morte del Santo -
  dichiarato dalla stessa "EDITOR'S NOTE" del PDF) NON ha un'intestazione
  propria per il primo blocco (Penitenza, QQ[1]-28): diventa "Treatise on
  Penance" per coerenza con gli altri file. I successivi quattro blocchi
  hanno intestazione bare-noun esplicita con range QQ proprio: "EXTREME
  UNCTION (QQ[29]-33)", "HOLY ORDERS (QQ[34]-40)", "MATRIMONY (QQ[41]-67)",
  poi "TREATISE ON THE RESURRECTION (QQ[69]-86)" e "TREATISE ON THE LAST
  THINGS (QQ[86]-99)" (quest'ultimo include, senza intestazione propria,
  le due Appendici finali su Purgatorio - restano nello stesso file).

APPARATO SCARTATO:
- pagine indice 0-152: copertina, "About This Book", intero Table of
  Contents, pagina del titolo interno del corpo con dati di edizione.
- pagine indice 4184-4200: Index of Scripture References (tabelle
  citazione biblica -> numero di pagina, niente testo di Tommaso).
- piede di pagina ripetuto su OGNI pagina del corpo (numero + "Saint
  Thomas Aquinas" + "Summa Theologica"): rimosso via regex.
- il paragrafo "EDITOR'S NOTE:" in apertura del Supplement (pagina indice
  3576): nota editoriale del compilatore sulla morte di Tommaso, non testo
  di Tommaso - rimosso; il testo del Supplement riparte da "OF THE PARTS
  OF PENANCE...", che e' testo (compilato ma) attribuito a Tommaso.
"""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

from .common import Work
from .sources import Source

# Sovrascrivibile via env, come RAW_ROOT: il PDF non vive sotto RAW_ROOT
# (notebooklm) ma in una cartella dedicata con altri PDF/video da ignorare.
AQUINAS_ROOT = os.environ.get(
    "PHILOSOPHY_AQUINAS_ROOT",
    r"E:/giovanni/Dropbox/remotedir/libri/libri_svago/Saggi/spiritualita_cristiana/Aquinas",
)

# pagina PDF di inizio (indice fitz, 0-based) - SOLO documentazione/sanity
# check, non usata per tagliare: un'intestazione di trattato NON e' sempre
# la prima riga della sua pagina (es. "TREATISE ON GRACE (QQ[109]-114)" cade
# a meta' di pagina 1649, con la coda del trattato "Law" prima di lei sulla
# STESSA pagina). Tagliare per pagina intera, come in una prima versione di
# questo adapter, faceva perdere la coda a "Law" e la faceva ricomparire in
# testa a "Grace": scoperto confrontando la prima riga di ogni file emesso
# con l'intestazione attesa (vedi verifica). Il taglio vero e' quindi per
# POSIZIONE DI TESTO (ricerca sequenziale della stringa di intestazione nel
# testo intero del corpo, `pos` che avanza — stesso principio di
# delphi_body.py/ortega.py), non per pagina.
BODY_START = 153   # 'FIRST PART (FP: QQ 1-119)'
BODY_END = 4183    # ultima pagina prima dell'Index of Scripture References
INDEX_START = 4184

# (titolo pubblicato, Parte di provenienza, stringa di intestazione da
# cercare nel testo ripulito - la prima riga del blocco, sufficiente a
# essere univoca; per i 4 trattati che aprono una Parte la chiave e' la riga
# della Parte stessa, cosi' quell'intestazione resta nel file). Pagina PDF
# indicata a fianco solo come riferimento per chi verifica a mano.
TREATISES: list[tuple[str, str, str]] = [
    ("Treatise on Sacred Doctrine", "First Part",
     "FIRST PART (FP: QQ 1-119)"),  # p153
    ("Treatise on the One God", "First Part",
     "TREATISE ON THE ONE GOD (QQ[2]-26)"),  # p163
    ("Treatise on the Most Holy Trinity", "First Part",
     "TREATISE ON THE MOST HOLY TRINITY (QQ[27]-43)"),  # p346
    ("Treatise on the Creation", "First Part",
     "TREATISE ON THE CREATION (QQ 44-49)"),  # p455
    ("Treatise on the Distinction of Things in General", "First Part",
     "TREATISE ON THE DISTINCTION OF THINGS IN GENERAL (Q[47])"),  # p477
    ("Treatise on the Distinction of Good and Evil", "First Part",
     "TREATISE ON THE DISTINCTION OF GOOD AND EVIL (QQ[48]-49)"),  # p481
    ("Treatise on the Angels", "First Part",
     "TREATISE ON THE ANGELS (QQ[50]-64)"),  # p493
    ("Treatise on the Work of the Six Days", "First Part",
     "TREATISE ON THE WORK OF THE SIX DAYS (QQ[65]-74)"),  # p583
    ("Treatise on Man", "First Part",
     "TREATISE ON MAN (QQ[75]-102)"),  # p631
    ("Treatise on the Conservation and Government of Creatures", "First Part",
     "TREATISE ON THE CONSERVATION AND GOVERNMENT OF"),  # p822 (titolo va a capo)
    ("Treatise on the Last End", "First Part of the Second Part",
     "FIRST PART OF THE SECOND PART (FS) (QQ[1]-114)"),  # p927
    ("Treatise on Human Acts: Acts Peculiar to Man", "First Part of the Second Part",
     "TREATISE ON HUMAN ACTS: ACTS PECULIAR TO MAN (QQ[6]-21)"),  # p972
    ("Treatise on the Passions", "First Part of the Second Part",
     "TREATISE ON THE PASSIONS (QQ[22]-48)"),  # p1074
    ("Treatise on Habits", "First Part of the Second Part",
     "TREATISE ON HABITS (QQ[49]-54)"),  # p1214
    ("Treatise on the Virtues", "First Part of the Second Part",
     "TREATISE ON HABITS IN PARTICULAR (QQ[55]-89) GOOD HABITS,"),  # p1246 (titolo va a capo)
    ("Treatise on Vice and Sin", "First Part of the Second Part",
     "EVIL HABITS, i.e. VICES AND SINS (QQ[71]-89)"),  # p1350
    ("Treatise on Law", "First Part of the Second Part",
     "TREATISE ON LAW (QQ 90-108)"),  # p1479
    ("Treatise on Grace", "First Part of the Second Part",
     "TREATISE ON GRACE (QQ[109]-114)"),  # p1649
    ("Treatise on the Theological Virtues", "Second Part of the Second Part",
     "SECOND PART OF THE SECOND PART (SS) (QQ[1]-189)"),  # p1703
    ("Treatise on the Cardinal Virtues", "Second Part of the Second Part",
     "TREATISE ON THE CARDINAL VIRTUES (QQ[47]-170)"),  # p2001
    ("Treatise on Fortitude and Temperance", "Second Part of the Second Part",
     "TREATISE ON FORTITUDE AND TEMPERANCE (QQ[123]-170)"),  # p2431
    ("Treatise on Gratuitous Graces", "Second Part of the Second Part",
     "TREATISE ON GRATUITOUS GRACES (QQ[171]-182)"),  # p2671
    ("Treatise on the States of Life", "Second Part of the Second Part",
     "TREATISE ON THE STATES OF LIFE (QQ[183]-189)"),  # p2745
    ("Treatise on the Incarnation", "Third Part",
     "THIRD PART (TP) OF THE SUMMA THEOLOGICA"),  # p2840
    ("Treatise on the Sacraments", "Third Part",
     "TREATISE ON THE SACRAMENTS (QQ[60]-90)"),  # p3272
    ("Treatise on Penance", "Supplement",
     "SUPPLEMENT (XP): TO THE THIRD PART OF THE SUMMA"),  # p3576 (titolo va a capo)
    ("Treatise on Extreme Unction", "Supplement",
     "EXTREME UNCTION (QQ[29]-33)"),  # p3698
    ("Treatise on Holy Orders", "Supplement",
     "HOLY ORDERS (QQ[34]-40)"),  # p3717
    ("Treatise on Matrimony", "Supplement",
     "MATRIMONY (QQ[41]-67)"),  # p3758
    ("Treatise on the Resurrection", "Supplement",
     "TREATISE ON THE RESURRECTION (QQ[69]-86)"),  # p3917
    ("Treatise on the Last Things", "Supplement",
     "TREATISE ON THE LAST THINGS (QQ[86]-99)"),  # p4057
]

# Piede di pagina ripetuto su ogni pagina del corpo: "<numero>\nSaint Thomas
# Aquinas\nSumma Theologica\n". Nessuna intestazione in testa pagina (solo
# piede) - verificato su decine di pagine campione in tutte le Parti.
_FOOTER_RE = re.compile(r"\n\d{1,4}\nSaint Thomas Aquinas\nSumma Theologica\n?")

# Nota editoriale in apertura del Supplement (pagina 3576): non e' testo di
# Tommaso, va rimossa. Stringa di inizio/fine verificata sul testo reale.
_EDITORS_NOTE_RE = re.compile(
    r"EDITOR'S NOTE:.*?ad 2 of the Supplement\.\n",
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# RICOSTRUZIONE DEI PARAGRAFI (Quaestio -> Articulus -> Obiezioni/Sed contra/
# Respondeo/Repliche).
#
# STRUTTURA DICHIARATA PRIMA DEL PARSER (verificata riga per riga su TUTTI e
# 31 i trattati, ~165.000 righe fisiche PDF, con script di analisi separati -
# non su un campione): fitz.get_text() ritorna le righe FISICHE di stampa del
# PDF, senza NESSUNA riga vuota (0,1% del totale, quasi tutte residuo di
# artefatti). I confini veri fra unita' di testo non sono nelle righe vuote
# (che qui non esistono) ma in marcatori lessicali fissi, sempre a INIZIO di
# una riga fisica, verificati come segue:
#
#   - "Objection <N>:" o "Objection <N>."  (10.528 occorrenze, N=1..17):
#     0 falsi positivi in tutto il corpus (le uniche righe che iniziano per
#     "Objection" senza numero subito dopo, es. "Objection is evident." o
#     "Objection.", sono continuazioni di frase spezzate dal print-wrap, MAI
#     un'intestazione: escluse richiedendo \d+ subito dopo "Objection").
#   - "Reply to Objection <N>:" (9.942 occorrenze): stesso controllo, 0 falsi
#     positivi; il numero di Reply e' sempre <= il numero di Objection nello
#     stesso articolo (Tommaso non risponde sempre a ogni obiezione con una
#     Reply numerata propria - a volte la risposta e' assorbita in un'altra
#     Reply - differenza normale, non un errore di parsing).
#   - "On the contrary" (3.044 occorrenze) e "I answer that" (3.120,
#     variante frequente senza virgola "I answer that As stated..."): 0 falsi
#     positivi verificati (le poche righe precedenti che sembravano non finire
#     con punteggiatura erano refusi di estrazione PDF che hanno perso il
#     punto finale, non testo che continua).
#   - Intestazione di QUAESTIO: riga che finisce con "(<NUMERO IN LETTERE>
#     ARTICLE[S])", es. "OF THE ESSENCE OF LAW (FOUR ARTICLES)" - 562
#     occorrenze, 0 falsi positivi nel corpus (numeri usati: ONE..SEVENTEEN,
#     mai in cifre). In 67 casi il titolo va a capo su due righe fisiche
#     (es. "...ON WHAT PART OF\nTHE BODY? (SEVEN ARTICLES)"): la riga
#     precedente va ricongiunta SOLO se e' anch'essa tutta maiuscola (come lo
#     e' sempre la seconda meta' di un titolo andato a capo: _is_capsy) E non
#     e' gia' un'altra intestazione E non finisce con punteggiatura terminale
#     ne' con ")"/"]" da soli - il solo controllo di punteggiatura, provato
#     per primo, non bastava: una citazione chiusa fra virgolette ("...are
#     most\nuseful in war and peace."\nOF MARTYRDOM (FIVE ARTICLES)") finisce
#     con '."' non con '.' nudo, e una riga di prosa ordinaria puo' finire
#     con una virgola a meta' frase senza per questo essere la testa di un
#     titolo - il requisito "maiuscola" e' quello che davvero distingue le
#     due meta' di un titolo andato a capo da un paragrafo di prosa adiacente
#     (bug trovato e corretto durante la verifica: senza il controllo
#     "maiuscola" la coda di una citazione finiva incollata dentro il titolo
#     della Questione successiva, sparendo dal corpo dell'articolo - vedi
#     Treatise_on_Law "...that lex is derived from legere because it is
#     written." + "OF THE VARIOUS KINDS OF LAW"). Questo esclude sia
#     l'intestazione di Trattato (finisce sempre con ")": "TREATISE ON LAW
#     (QQ 90-108)") sia le etichette a se' stanti con singola Questione fra
#     parentesi quadre (es. "VICES OPPOSED TO DISTRIBUTIVE JUSTICE (Q[63])",
#     gia' documentate sopra come NON confini di trattato) sia i riferimenti
#     bibliografici di fine riga (es. "(Q[13], A[5])."). Verificato
#     campionando tutte le 562 occorrenze e confermando 0 fusioni spurie dopo
#     il fix (script di analisi separati, non nel repo).
#   - Intestazione di ARTICULUS: quasi sempre la domanda stessa, "Whether
#     ...?" (3.182 righe che iniziano per "Whether"; il 96,9% e' seguito
#     immediatamente da "Objection 1:", verificato posizionalmente). Tre
#     varianti minori, lasciate SENZA intestazione dedicata (l'articolo resta
#     comunque un paragrafo separato, confluisce nel testo del blocco
#     precedente - nessun testo viene perso, solo il titolo esplicito manca):
#       (a) Questione con un solo Articolo, dove la domanda non e' ripetuta
#           separatamente (es. "OF THE WORK OF THE FIFTH DAY (ONE ARTICLE)\n
#           We must next consider the work of the fifth day.\nObjection 1:");
#       (b) 4 casi nel trattato sulla Trinita' con titolo nominale invece che
#           interrogativo ("The definition of "person"", senza "?");
#       (c) domanda che va a capo su piu' righe fisiche (83 casi, fino a 6
#           righe quando la nota del traduttore fra parentesi quadre e' lunga
#           e a sua volta va a capo): ricongiunta in avanti fino alla prima
#           riga che chiude con "?" (eventualmente seguito da una nota "[...]"
#           chiusa sulla STESSA riga) entro una finestra di sicurezza; oltre
#           la finestra (nota fra parentesi troppo lunga, 18 casi) si rinuncia
#           alla ricongiunzione invece di indovinare - stesso principio "non
#           nascondere il difetto" del safety net di split.py.
#
# Il join dei "candidati" verificato su tutto il corpus (32 trattati, script
# di analisi in fase di sviluppo): 0 falsi positivi per Objection/Reply/On
# the contrary/I answer that; l'unico rischio reale erano le abbreviazioni
# con punto (Q[1], A[2], FP, SS, Obj. 3, i.e., Rom. 5:12): NESSUNA di queste
# comincia una riga fisica con uno dei marcatori sopra, quindi il fatto che
# "taglio = riga che INIZIA col marcatore" (non "frase che finisce col
# punto") le rende innocue per costruzione - il parser non guarda MAI la
# punteggiatura di fine riga per decidere un taglio, solo l'inizio riga.
#
# COSA DIVENTA UN ATOMO: solo QUAESTIO e ARTICULUS diventano intestazioni
# riconosciute da scripts/atomize/headings.py (vedi ARTICULUS/QUAESTIO in
# quel file) - Objection/Reply/On the contrary/I answer restano paragrafi
# ordinari SEPARATI da riga vuota (cosi' un articolo troppo lungo per
# MAX_WORDS viene comunque impacchettato da split.py su confini di paragrafo
# veri, mai a meta' frase) ma NON tagliano un nuovo atomo: un atomo = un
# Articulus intero (obiezioni + sed contra + respondeo + repliche), che è
# l'unita' che la Summa stessa dichiara con la propria domanda.
# ---------------------------------------------------------------------------

_ARTICLE_NUMBER_WORD = (
    r"(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|"
    r"THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|"
    r"TWENTY(?:-\w+)?|THIRTY(?:-\w+)?)"
)

_OBJ_RE = re.compile(r"^Objection\s+\d+\s*[:.]")
_REPLY_RE = re.compile(r"^Reply to Objection\s+\d+\s*[:.]")
_ONCONTRARY_RE = re.compile(r"^On the contrary\b")
_IANSWER_RE = re.compile(r"^I answer that\b")
_QUAESTIO_END_RE = re.compile(
    rf"\({_ARTICLE_NUMBER_WORD}\s+ARTICLES?\)\s*$"
)
_WHETHER_START_RE = re.compile(r"^Whether\b")
_WHETHER_END_RE = re.compile(r"\?\s*(?:\[[^\]]*\])?\.?\s*[\"'”’]?\s*$")
# righe da NON ricongiungere all'indietro in una QUAESTIO: finiscono con
# punteggiatura terminale (con o senza virgoletta/parentesi di chiusura dopo
# - la Summa cita in continuazione: "...are most\nuseful in war and peace."
# \nOF MARTYRDOM (FIVE ARTICLES)", la riga della citazione finisce per
# costruzione con '."', non semplicemente '.') oppure finiscono da sole con
# ")" o "]" senza punto prima (intestazioni di Trattato "...(QQ[71]-89)",
# etichette "(Q[N])" a se' stanti: qui la parentesi NON segue un punto).
_NOT_MERGEABLE_TAIL_RE = re.compile(r"(?:[.:;!?][\]\)\"'”’]*|[\]\)])\s*$")

_WHETHER_JOIN_WINDOW = 5  # righe fisiche max per ricongiungere una domanda


def _is_capsy(s: str) -> bool:
    """True se `s` ha almeno una lettera e nessuna minuscola: e' il modo in
    cui questa edizione stampa SEMPRE i titoli di Trattato/Questione. Serve
    a distinguere la vera seconda meta' di un titolo andato a capo (anche
    lei in maiuscolo) da una riga di prosa ordinaria che semplicemente non
    finisce con un segno di punteggiatura forte (es. una virgola a meta'
    frase) - la sola punteggiatura di fine riga non basta a deciderlo."""
    return any(c.isalpha() for c in s) and s == s.upper()


def _is_marker_start(s: str) -> bool:
    return bool(
        _OBJ_RE.match(s) or _REPLY_RE.match(s) or _ONCONTRARY_RE.match(s)
        or _IANSWER_RE.match(s) or _WHETHER_START_RE.match(s)
        or _QUAESTIO_END_RE.search(s)
    )


_BRACKET_RE = re.compile(r"\[[^\]]*\]")


def _quaestio_title_start(s: str) -> int:
    """Indice in `s` dove comincia il VERO titolo di Quaestio, quando la
    stampa PDF ha incollato sulla stessa riga fisica la coda della frase
    precedente e l'intestazione (36 casi su 562, es. Treatise_on_Law: 'says
    (Etym. v, 3; ii, 10) that "lex is derived..." OF THE VARIOUS KINDS OF
    LAW (SIX ARTICLES)' e' UNA riga PDF sola, non due). Il titolo vero e'
    sempre in maiuscolo (converzione della stessa edizione per Trattato/
    Questione, verificata su tutte le 562 occorrenze); la prosa che lo
    precede non lo e' mai. Cerca quindi, a partire da destra, l'ULTIMA
    parola (fuori da una nota del traduttore fra parentesi quadre, che
    resta minuscola per costruzione: es. "[*Excessive daring...]") che
    contiene una lettera minuscola: il titolo comincia subito dopo. Ritorna
    0 se l'intera riga e' gia' maiuscola (nessuna prosa incollata: o la
    riga e' un titolo completo, o e' la seconda meta' di un titolo andato
    a capo sulla riga PRIMA - gestito separatamente sotto)."""
    brackets = [m.span() for m in _BRACKET_RE.finditer(s)]

    def in_bracket(pos: int) -> bool:
        return any(a <= pos < b for a, b in brackets)

    start = 0
    for m in reversed(list(re.finditer(r"\S+", s))):
        if in_bracket(m.start()):
            continue
        if any(c.islower() for c in m.group()):
            start = m.end()
            while start < len(s) and s[start] == " ":
                start += 1
            break
    return start


def _merge_wrapped_headings(lines: list[str]) -> list[str]:
    """Ricongiunge QUAESTIO e ARTICULUS andati a capo (o incollati) sul
    print PDF.

    Ritorna una nuova lista di righe della STESSA lunghezza (le righe
    consumate dal merge diventano stringhe vuote, mai rimosse: gli indici
    delle righe successive non si spostano)."""
    lines = list(lines)

    # QUAESTIO, due casi distinti (entrambi verificati sul corpus intero):
    #  (a) prosa e intestazione INCOLLATE sulla stessa riga fisica (36 casi):
    #      si separano con _quaestio_title_start, la prosa resta con la riga
    #      non vuota precedente (ricostruisce l'unica frase originale).
    #  (b) l'intestazione stessa va a capo su due righe fisiche (67 casi,
    #      vedi TREATISES/commento sopra): la riga PRIMA va ricongiunta SE
    #      non e' gia' un'altra intestazione e non finisce con punteggiatura
    #      terminale ne' con ")" (esclude intestazioni di Trattato, etichette
    #      "(Q[N])" a se' stanti, riferimenti bibliografici).
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or not _QUAESTIO_END_RE.search(s):
            continue
        title_start = _quaestio_title_start(s)
        if title_start > 0:
            prefix, suffix = s[:title_start].rstrip(), s[title_start:]
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            if j < 0:
                continue  # nessuna riga precedente dove appoggiare la prosa: rinuncia
            lines[j] = (lines[j].rstrip() + " " + prefix) if lines[j].strip() else prefix
            lines[i] = suffix
            continue
        if i == 0:
            continue
        prev = lines[i - 1].strip()
        if (
            not prev
            or _is_marker_start(prev)
            or _NOT_MERGEABLE_TAIL_RE.search(prev)
            or not _is_capsy(prev)
        ):
            continue
        lines[i] = prev + " " + s
        lines[i - 1] = ""

    # ARTICULUS: la domanda "Whether ...?" a volte va a capo su piu' righe.
    # Ricongiunge IN AVANTI finche' non trova una riga che chiude con "?"
    # (eventualmente seguito da una nota del traduttore fra parentesi quadre
    # chiusa sulla stessa riga), entro una finestra di sicurezza; oltre la
    # finestra rinuncia (la domanda resta spezzata, non diventa intestazione
    # riconosciuta - vedi commento sopra, e' un compromesso dichiarato, non
    # un bug nascosto).
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s and _WHETHER_START_RE.match(s) and not _WHETHER_END_RE.search(s):
            parts = [s]
            j = i + 1
            consumed = []
            found = False
            while j < len(lines) and j < i + _WHETHER_JOIN_WINDOW:
                nxt = lines[j].strip()
                if not nxt or _is_marker_start(nxt):
                    break  # un'altra unita' comincia: la domanda non chiude, rinuncia
                parts.append(nxt)
                consumed.append(j)
                if _WHETHER_END_RE.search(nxt):
                    found = True
                    break
                j += 1
            if found:
                lines[i] = " ".join(parts)
                for k in consumed:
                    lines[k] = ""
                i = j
        i += 1

    return lines


# "On the contrary" e "I answer that" cominciano quasi sempre una riga
# fisica propria (vedi verifica sopra), ma in 36+1 casi il print PDF li
# incolla sulla stessa riga di un'obiezione cortissima ("Objection 4: On
# the contrary, Tully says..."): 0 falsi positivi verificati (a differenza
# di Objection/Reply, un "On the contrary"/"I answer that" embedded a meta'
# riga fisica non e' MAI continuazione di frase - sono locuzioni fisse che
# in Tommaso compaiono solo in apertura di queste due parti dell'articolo).
_EMBEDDED_ONCONTRARY_RE = re.compile(r"(?<!^)On the contrary\b")
_EMBEDDED_IANSWER_RE = re.compile(r"(?<!^)I answer that\b")


def _split_embedded_markers(lines: list[str]) -> list[str]:
    """Spacca una riga fisica quando contiene un secondo marcatore incollato
    a meta' (vedi commento sopra). Puo' allungare la lista: qui e' sicuro,
    e' l'ultimo passo prima della ricomposizione finale in
    _reconstruct_paragraphs, nessun indice viene piu' riletto dopo."""
    out: list[str] = []
    for line in lines:
        s = line
        while True:
            m = _EMBEDDED_ONCONTRARY_RE.search(s) or _EMBEDDED_IANSWER_RE.search(s)
            if not m:
                break
            out.append(s[: m.start()].rstrip())
            s = s[m.start():]
        out.append(s)
    return out


def _reconstruct_paragraphs(text: str) -> str:
    """Inserisce una riga vuota prima di ogni marcatore strutturale.

    E' l'UNICA cosa che serve per far ricomparire i paragrafi: split.py
    definisce un paragrafo come righe non vuote consecutive, quindi basta
    segnare dove finisce l'unita' precedente perche' Objection/Reply/On the
    contrary/I answer that/Quaestio/Articulus tornino a essere paragrafi
    separati - non serve toccare il testo dentro ogni unita', che resta
    quello che fitz ha estratto (le righe di stampa originali, ora solo
    raggruppate correttamente)."""
    lines = text.split("\n")
    lines = _merge_wrapped_headings(lines)
    lines = _split_embedded_markers(lines)

    out: list[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if _is_marker_start(s) and out and out[-1].strip():
            out.append("")
        out.append(line)
    return "\n".join(out)


def find_pdf(source: Source) -> Path:
    pattern = str(Path(AQUINAS_ROOT) / source.glob)
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"nessun PDF per {source.key}: {pattern}")
    if len(paths) > 1:
        raise FileNotFoundError(
            f"piu' di un PDF per {source.key}, adapter si aspetta uno solo: {paths}"
        )
    return Path(paths[0])


@dataclass
class ExtractResult:
    works: list[Work] = field(default_factory=list)
    toc_titles: list[str] = field(default_factory=list)


def extract(pdf_path: Path) -> ExtractResult:
    doc = fitz.open(pdf_path)
    try:
        if len(doc) <= BODY_END:
            raise ValueError(
                f"PDF ha solo {len(doc)} pagine, attese almeno {BODY_END + 1}: "
                "struttura cambiata rispetto a quella verificata"
            )
        raw = "".join(doc[p].get_text() for p in range(BODY_START, BODY_END + 1))
    finally:
        doc.close()

    # Piede di pagina ripulito UNA VOLTA su tutto il corpo (non trattato per
    # trattato): elimina ogni "cucitura" fra pagine consecutive prima di
    # cercare le intestazioni, cosi' una riga di intestazione mai spezzata
    # da un piede resta cercabile come stringa singola.
    text = _FOOTER_RE.sub("\n", raw)
    text = _EDITORS_NOTE_RE.sub("", text)

    # Ricostruzione dei paragrafi PRIMA della ricerca delle intestazioni di
    # Trattato: inserisce righe vuote, non tocca il contenuto delle chiavi
    # TREATISES (nessuna comincia per "Whether" o finisce per "(N
    # ARTICLES)", vedi commento sopra) - le posizioni restano trovabili
    # con lo stesso text.find() sequenziale di sempre, solo su testo con i
    # paragrafi veri gia' dentro.
    text = _reconstruct_paragraphs(text)

    # Ricerca POSIZIONALE e sequenziale (pos avanza), come delphi_body.py:
    # ogni intestazione viene cercata solo DOPO la precedente, cosi' un
    # trattato non puo' "rubare" testo a quello prima di lui ne' matchare
    # per errore un'occorrenza ripetuta piu' avanti nel libro.
    positions: list[int] = []
    pos = 0
    for title, _part, key in TREATISES:
        idx = text.find(key, pos)
        if idx == -1:
            raise ValueError(f"intestazione non trovata per {title!r}: {key!r}")
        positions.append(idx)
        pos = idx + len(key)

    works: list[Work] = []
    for i, (title, part, _key) in enumerate(TREATISES):
        start = positions[i]
        end = positions[i + 1] if i + 1 < len(TREATISES) else len(text)
        body = re.sub(r"\n{3,}", "\n\n", text[start:end]).strip()
        if not body:
            raise ValueError(f"corpo vuoto per {title!r}")
        works.append(Work(title=title, text=body, kind="work", tomo=part))
    return ExtractResult(works=works, toc_titles=[t for t, _, _ in TREATISES])
