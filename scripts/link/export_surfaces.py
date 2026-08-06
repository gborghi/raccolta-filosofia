"""Esporta per il build del sito la tavola delle superfici linkabili.

    python scripts/link/export_surfaces.py

Il sito lo costruisce node (`preprocess.mjs`), ma cosa regga un link e cosa no
lo decide `vocab.py`, e quella decisione deve stare in un posto solo. La
stoplist non e' una lista di preferenze: ogni voce e' un errore visto sul corpus
("will" ausiliare, "cause" in "the royal cause", "virtue" in "in virtue of").
Riscriverla in JavaScript significherebbe due copie che divergono al primo
ritocco, e la copia sbagliata sarebbe quella che il lettore vede.

Quindi qui non c'e' nessuna regola: si chiama `linkable_surfaces()` e si scrive
il risultato in `data/link_surfaces.json`. preprocess.mjs lo legge e non sa
nulla di soglie, omonimie o nomi di filosofi.

La frequenza documentale viene misurata sul corpus *corrente* invece di leggere
`data/link_docfreq.json`: quel file e' di `run.py` (che ci scrive i propri
wikilink nel vault) e puo' essere vecchio di un'atomizzazione. La soglia sulle
superfici generiche e' una frazione degli atomi, quindi misurarla su un corpus
che non esiste piu' vorrebbe dire tararla su un altro corpus.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run import DOCFREQ, atom_paths, report  # noqa: E402
from vocab import REPO, all_surfaces, linkable_surfaces, load_taxonomy  # noqa: E402

OUT = os.path.join(REPO, "data", "link_surfaces.json")


def main():
    paths = atom_paths()
    _, freq = report(paths)
    tax = load_taxonomy()
    table = linkable_surfaces(freq, tax, n_docs=len(paths))
    payload = {
        "_readme": (
            "Generato da scripts/link/export_surfaces.py: non si edita a mano. "
            "Le regole stanno in scripts/link/vocab.py, i consumatori in "
            "quartz-philosophy/preprocess.mjs."
        ),
        "n_docs": len(paths),
        "surfaces": {s: table[s] for s in sorted(table)},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    dropped = len(all_surfaces(tax)) - len(table)
    print(
        f"{OUT}: {len(table)} superfici linkabili su {len(paths)} atomi "
        f"({dropped} scartate: generiche o ambigue)"
    )
    if not os.path.exists(DOCFREQ):
        print(f"nota: {DOCFREQ} assente: run.py lo rigenera da solo alla prossima corsa")
    return 0


if __name__ == "__main__":
    sys.exit(main())
