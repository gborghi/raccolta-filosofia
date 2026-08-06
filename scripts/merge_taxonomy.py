"""Fonde i frammenti data/taxonomy_add_*.json in data/taxonomy.json.

    python scripts/merge_taxonomy.py --dry-run
    python scripts/merge_taxonomy.py

Il vocabolario e' cresciuto per domini (greco, scolastica, moderni) scritti in
parallelo su frammenti separati, per non farli collidere sullo stesso file.
Fonderli non e' un `update()`: due cose si rompono in silenzio.

1. UN ASSE TIENE LA PROPRIA LISTA DI POSIZIONI. Una position nuova che dichiara
   `axis: "human_nature"` NON compare sull'asse finche' il suo id non e' anche
   dentro `human_nature.positions`. Il nodo esisterebbe, il tagging lo userebbe,
   e la pagina dell'asse non lo mostrerebbe mai. Tutti e tre gli autori dei
   frammenti hanno segnalato questo punto per conto proprio.

2. GLI ID SONO PER SEMPRE. Sono il bersaglio dei wikilink gia' scritti nel vault
   e dei tag gia' assegnati: un id che cambia o che collide spezza i link senza
   un errore. Qui si aggiunge soltanto — mai rinominare, mai sovrascrivere.

Percio' il merge valida e si ferma al primo problema, invece di scrivere un
vocabolario incoerente.
"""

import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, ".."))
TAXONOMY = os.path.join(REPO, "data", "taxonomy.json")
FRAGMENTS = os.path.join(REPO, "data", "taxonomy_add_*.json")

CATEGORIES = ("axes", "positions", "schools", "forms", "concepts", "arguments", "figures")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def all_ids(tax):
    return {n["id"] for cat in CATEGORIES for n in tax.get(cat, [])}


def validate(tax):
    """Ritorna la lista dei problemi. Vuota = coerente."""
    problems = []
    ids = {}
    for cat in CATEGORIES:
        for n in tax.get(cat, []):
            if n["id"] in ids:
                problems.append(f"id duplicato: {n['id']} (in {ids[n['id']]} e {cat})")
            ids[n["id"]] = cat

    axis_ids = {n["id"] for n in tax.get("axes", [])}
    pos_by_id = {n["id"]: n for n in tax.get("positions", [])}

    for p in tax.get("positions", []):
        ax = p.get("axis")
        if ax and ax not in axis_ids:
            problems.append(f"position {p['id']}: axis '{ax}' non esiste")
        # Il legame e' bidirezionale: senza questo, la posizione e' orfana.
        if ax:
            listed = next((a for a in tax["axes"] if a["id"] == ax), None)
            if listed and p["id"] not in (listed.get("positions") or []):
                problems.append(
                    f"position {p['id']}: non elencata in {ax}.positions (sarebbe invisibile)"
                )
        for c in p.get("contro") or []:
            if c not in pos_by_id and c not in ids:
                problems.append(f"position {p['id']}: contro '{c}' non esiste")

    for a in tax.get("axes", []):
        for pid in a.get("positions") or []:
            if pid not in pos_by_id:
                problems.append(f"axis {a['id']}: position '{pid}' non esiste")

    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    tax = load(TAXONOMY)
    base_ids = all_ids(tax)
    print(f"base: {len(base_ids)} nodi")

    frags = sorted(glob.glob(FRAGMENTS))
    if not frags:
        print("nessun frammento da fondere")
        return 1

    added = {c: 0 for c in CATEGORIES}
    wired = []
    seen = set(base_ids)

    for f in frags:
        frag = load(f)
        name = os.path.basename(f)
        n_here = 0
        for cat in CATEGORIES:
            for node in frag.get(cat, []):
                if node["id"] in seen:
                    # Fail-closed: un id che collide e' un errore di progetto, non
                    # qualcosa da risolvere in automatico scegliendone uno.
                    print(f"ERRORE: {name} ridefinisce l'id esistente '{node['id']}'")
                    return 1
                seen.add(node["id"])
                tax.setdefault(cat, []).append(node)
                added[cat] += 1
                n_here += 1
        print(f"  {name}: +{n_here} nodi")

    # Aggancia ogni position nuova al suo asse. E' il passo che un update()
    # dimenticherebbe, lasciando nodi orfani.
    by_axis = {a["id"]: a for a in tax.get("axes", [])}
    for p in tax.get("positions", []):
        ax = p.get("axis")
        if not ax or ax not in by_axis:
            continue
        lst = by_axis[ax].setdefault("positions", [])
        if p["id"] not in lst:
            lst.append(p["id"])
            wired.append(f"{p['id']} -> {ax}")

    if wired:
        print(f"\nagganciate {len(wired)} posizioni al loro asse:")
        for w in wired:
            print(f"  {w}")

    problems = validate(tax)
    if problems:
        print(f"\n{len(problems)} PROBLEMI — non scrivo nulla:")
        for p in problems[:20]:
            print(f"  - {p}")
        return 1

    total = len(all_ids(tax))
    print(f"\ncoerente. {len(base_ids)} -> {total} nodi (+{total - len(base_ids)})")
    for c in CATEGORIES:
        if added[c]:
            print(f"  {c}: +{added[c]}")

    if args.dry_run:
        print("\n--dry-run: niente scritto")
        return 0

    with open(TAXONOMY, "w", encoding="utf-8", newline="") as fh:
        json.dump(tax, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"\nscritto {TAXONOMY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
