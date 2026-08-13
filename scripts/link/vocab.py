"""Superfici linkabili ricavate dal vocabolario controllato.

Il tagging e l'interlinking usano lo stesso vocabolario ma hanno bisogni
opposti, e questo modulo esiste per tenerli separati.

Per il tagging un alias generico va benissimo: "experience" e' davvero un
indizio di empirismo, e un tag in piu' su un brano di Hume non fa danno. Come
innesco di un wikilink inline lo stesso alias e' un disastro — Hume scrive
"experience" centinaia di volte, e linkarle tutte trasformerebbe il testo in
una distesa di link azzurri che nessuno segue.

Quindi: `linkable_surfaces()` restituisce il sottoinsieme delle superfici
abbastanza precise da reggere un link nel corpo del testo. Il criterio e'
misurato sul corpus, non deciso a mano (vedi `run.py --report`).
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
TAXONOMY = os.path.join(REPO, "data", "taxonomy.json")

CATEGORIES = ("axes", "positions", "schools", "forms", "concepts", "arguments", "figures")

# I `forms` sono etichette di genere: dicono che l'opera E' un saggio, un
# trattato, una lettera. Non sono concetti di cui il testo parla. La parola
# "essay" dentro la prosa di Locke non e' un rinvio alla nozione di saggio, e
# linkarla aggiungerebbe solo rumore (essay 331 atomi, treatise 225, critique
# 182). L'aggregatore per forma resta popolato dal tagging, che su questo lavora
# bene proprio perche' guarda l'opera e non la singola frase.
LINK_CATEGORIES = ("axes", "positions", "schools", "concepts", "arguments", "figures")

# Una superficie monoparola presente in piu' di questa frazione di atomi e'
# prosa comune, non un termine tecnico: come innesco di link va scartata.
# Le multiparola ("eternal recurrence", "tabula rasa") non passano da qui —
# sono precise per costruzione.
GENERIC_DOC_RATIO = 0.08

# I nodi `figures` portano fra gli alias il nome del filosofo a cui la figura
# appartiene: `lucilius` ha "Seneca", `master_and_slave` ha "Hegel",
# `the_libertine` ha "Pascal", `malin_genie` ha "Descartes". E' un indizio per il
# tagger — dice di chi e' la figura — non una forma con cui la figura compare nel
# testo. Come innesco di link sarebbe rovinoso: ogni "Hegel" dentro Hegel
# diventerebbe un link alla dialettica servo-padrone.
#
# Oggi la regola sull'ambiguita' li scarta gia' (ogni nome e' rivendicato anche
# dalla sua scuola), ma per caso, non per scelta: basterebbe togliere un alias
# altrove per farli riemergere. Qui la scelta e' esplicita.
PHILOSOPHER_NAMES = {
    "seneca", "hegel", "pascal", "descartes", "cartesio", "kant", "hume",
    "locke", "marx", "lucretius", "lucrezio", "nietzsche", "rousseau",
    "ortega", "aquinas",
}

# Alias che il tagger usa bene ma che non reggono un link inline. Ognuno
# verificato sul corpus, non supposto.
#
# Il filo comune: in inglese filosofico l'omonimia non segue la frequenza. Un
# termine puo' essere raro *e* ambiguo, quindi nessuna soglia lo prende — solo
# la lettura del testo.
LINK_STOPLIST = {
    # onorifico tedesco: "Herr von Haller", "Herr Tholuck", "Herr Moses" — e'
    # "Signor", non il padrone della dialettica. 107 atomi, nessuno pertinente.
    "herr",
    # descrive il ruolo di Lucilio (il destinatario delle Epistulae); non e' un
    # nome che compaia nel testo.
    "destinatario",
    # verbo: "the pressure of adversity does not affect the mind" (Seneca) — non
    # l'affectus di Spinoza.
    "affect",
    # patto qualsiasi: "a brave and noble compact with fate" (Seneca) — non il
    # contratto sociale.
    "compact",
    # bersaglio sbagliato: la coscienza morale non e' la liberta' di coscienza,
    # che e' una posizione politica su un altro asse. 349 atomi.
    "conscience",
    # generico e spesso verbo ("decline an offer"); decadence e' un'altra cosa.
    "decline",
    # generico: un esperimento non e' una tesi sull'induzione.
    "experiment",
    # generico: "tradition" nella prosa non e' la posizione "autorita' della
    # tradizione".
    "tradition",
    # in inglese e' la proporzione, non la ragione; il latino "ratio" del testo
    # di Lucrezio e' gia' coperto dagli altri alias latini.
    "ratio",
    # ablativo latino di "ars" ("arte" = con arte): non il concetto di bellezza.
    "arte",
    # aggettivo e pianta; la figura del saggio ha gia' il suo nodo the_sage.
    "sage",
    # alias di nominalism ("i nomi sono flatus vocis"): per il tagger e' un buon
    # indizio, come link e' rovinoso. In Agostino "names" e' quasi sempre "il
    # nome del Signore", "chiamare per nome", non la tesi sugli universali —
    # 235 atomi, nessuno nominalista. "nomi" per simmetria (il testo italiano
    # non entra nel linker, ma la superficie resta esclusa per scelta esplicita).
    "names",
    "nomi",
}


def load_taxonomy(path=TAXONOMY):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def all_surfaces(tax=None, categories=LINK_CATEGORIES):
    """superficie (lower) -> set di id canonici che la rivendicano."""
    tax = tax or load_taxonomy()
    surf = {}
    for cat in categories:
        for node in tax.get(cat, []):
            labels = [node.get("label_it"), node.get("label_en")]
            labels += list(node.get("aliases") or [])
            for s in labels:
                if not s:
                    continue
                surf.setdefault(s.strip().lower(), set()).add(node["id"])
    return surf


def word_count(surface):
    return len(surface.split())


def node_types(tax=None, categories=LINK_CATEGORIES):
    """superficie (lower) -> set dei tipi che la rivendicano."""
    tax = tax or load_taxonomy()
    out = {}
    for cat in categories:
        for node in tax.get(cat, []):
            labels = [node.get("label_it"), node.get("label_en")]
            labels += list(node.get("aliases") or [])
            for s in labels:
                if s:
                    out.setdefault(s.strip().lower(), set()).add(cat)
    return out


def linkable_surfaces(doc_freq, tax=None, ratio=GENERIC_DOC_RATIO, n_docs=None):
    """Filtra `all_surfaces` tenendo solo cio' che regge un link inline.

    doc_freq: superficie -> in quanti atomi compare (da `run.py --report`).
    Ritorna superficie -> {"id": str, "cap": bool}; `cap` chiede che il testo
    trovato sia maiuscolo.

    Le tre regole vengono dall'evidenza sul corpus, non da preferenze:

    - **multiparola: sempre.** "eternal recurrence", "state of nature",
      "tabula rasa" non hanno un secondo senso. Sono precise per costruzione.
    - **nome proprio (figures): sempre, ma solo se maiuscolo.** "Hume" nelle
      lezioni di Hegel e' il filosofo; "hume" minuscolo non esiste.
    - **altra monoparola: solo se rara.** Il campione mostra che la frequenza non
      misura l'importanza ma l'ambiguita': "cause" al 20% e' quasi sempre "the
      royal cause", "virtue" e' "in virtue of", "will" e' l'ausiliare. Sopravvive
      quindi solo il termine raro — che e' raro *perche'* e' tecnico
      ("apatheia", "cogito", "noumenon"). Si perde il link inline su "god" o
      "soul": li' l'aggregazione la porta gia' il tagging, che su un alias
      generico funziona benissimo proprio perche' non tocca la prosa.
    """
    tax = tax or load_taxonomy()
    surf = all_surfaces(tax)
    types = node_types(tax)
    labels = {}
    for cat in LINK_CATEGORIES:
        for node in tax.get(cat, []):
            for lab in (node.get("label_it"), node.get("label_en")):
                if lab:
                    labels.setdefault(lab.strip().lower(), set()).add(node["id"])
    out = {}
    for s, ids in surf.items():
        # Una superficie rivendicata da due nodi non ha un bersaglio: linkarla
        # significherebbe sceglierne uno a caso.
        if len(ids) != 1:
            continue
        if s in LINK_STOPLIST:
            continue
        node_id = next(iter(ids))
        # Il nome di un filosofo linka solo al nodo che porta quel nome come
        # etichetta (Hobbes -> hobbes), mai a un nodo che se lo tiene come
        # semplice alias (Hegel -> master_and_slave).
        if s in PHILOSOPHER_NAMES and node_id not in labels.get(s, set()):
            continue
        is_figure = types.get(s) == {"figures"}
        if word_count(s) > 1:
            out[s] = {"id": node_id, "cap": False}
        elif is_figure:
            out[s] = {"id": node_id, "cap": True}
        elif n_docs and doc_freq.get(s, 0) > n_docs * ratio:
            continue
        else:
            out[s] = {"id": node_id, "cap": False}
    return out


def surface_pattern(surfaces):
    """Un'unica regex alternata, ordinata dalla piu' lunga: cosi' "eternal
    recurrence" vince su "recurrence" invece di essere spezzata da essa."""
    if not surfaces:
        return None
    ordered = sorted(surfaces, key=len, reverse=True)
    body = "|".join(re.escape(s) for s in ordered)
    return re.compile(r"(?<![\w-])(" + body + r")(?![\w-])", re.IGNORECASE)
