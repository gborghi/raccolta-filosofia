"""Inserisce i wikilink del vocabolario controllato nel corpo degli atomi.

    python scripts/link/run.py --report    # misura la diffusione delle superfici
    python scripts/link/run.py --dry-run   # cosa linkerebbe, senza scrivere
    python scripts/link/run.py             # scrive nel vault

I link vanno **nel vault**, non generati al volo in preprocess: il vault e' un
vault Obsidian, e il grafo di Obsidian si nutre dei wikilink nei file. Generarli
solo a build time darebbe un sito linkato e un vault muto. In piu' i traduttori
hanno bisogno di vedere i link per preservarli (vedi scripts/translate/REGOLE.md).

Il bersaglio e' sempre l'ID canonico, l'etichetta e' il testo trovato:
`[[empiricism|experience]]`. Cosi' l'italiano puo' scrivere
`[[empiricism|esperienza]]` e puntare allo stesso nodo — che e' cio' che rende
il grafo language-agnostic.
"""

import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vocab import (  # noqa: E402
    REPO,
    all_surfaces,
    linkable_surfaces,
    load_taxonomy,
    surface_pattern,
)

# REPO e' quartz-philosophy/: data/ ci sta dentro, il vault gli e' fratello.
PHIL_DIR = os.path.normpath(os.path.join(REPO, "..", "VaultPhilosophy", "Philosophers"))
DOCFREQ = os.path.join(REPO, "data", "link_docfreq.json")

FM_RE = re.compile(r"\A(---\r?\n.*?\r?\n---[ \t]*\r?\n)", re.S)
WIKILINK_RE = re.compile(r"\[\[[^\]]*\]\]")

# Oltre questa soglia il brano smette di essere prosa e diventa un indice: il
# lettore salta i link invece di seguirli. Si linka la prima occorrenza di ogni
# concetto, non ogni occorrenza.
MAX_LINKS_PER_ATOM = 12


def atom_paths():
    out = []
    for root, _, names in os.walk(PHIL_DIR):
        if os.path.basename(root) == "_raw":
            continue
        for n in names:
            # Solo l'atomo base `NNN_slug.md`: le varianti di lingua
            # (`.it.md`, `.en.md`, il latino a fronte `.la.md`) non si linkano —
            # il vocabolario e' inglese e i loro link nascono dall'atomo base.
            if n.endswith(".md") and not re.search(r"\.[a-z]{2}\.md$", n):
                out.append(os.path.join(root, n))
    out.sort()
    return out


def split_fm(text):
    m = FM_RE.match(text)
    return (m.group(1), text[m.end():]) if m else ("", text)


def report(paths):
    """superficie -> in quanti atomi compare. Una regex sola, un passaggio per file."""
    surf = all_surfaces()
    pat = surface_pattern(list(surf))
    freq = collections.Counter()
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            body = split_fm(fh.read())[1].lower()
        for s in set(m.group(1).lower() for m in pat.finditer(body)):
            freq[s] += 1
    return surf, dict(freq)


def link_body(body, table, pat):
    """Inserisce i wikilink. Ritorna (nuovo_corpo, n_link)."""
    linked = set()
    count = 0

    def sub_line(line):
        nonlocal count
        # Gli heading restano nudi: un link in un titolo verrebbe emesso anche
        # nella barra del lettore SPA, dove non e' cliccabile.
        if line.lstrip().startswith("#"):
            return line
        out = []
        pos = 0
        # Salta le regioni gia' occupate da un wikilink, altrimenti il target di
        # un link esistente verrebbe linkato di nuovo dentro se stesso.
        for existing in WIKILINK_RE.finditer(line):
            out.append(replace_in(line[pos:existing.start()]))
            out.append(existing.group(0))
            pos = existing.end()
        out.append(replace_in(line[pos:]))
        return "".join(out)

    def replace_in(chunk):
        nonlocal count

        def one(m):
            nonlocal count
            surface = m.group(1)
            entry = table.get(surface.lower())
            if entry is None or count >= MAX_LINKS_PER_ATOM:
                return surface
            # I nomi propri linkano solo se il testo e' maiuscolo: la regex e'
            # case-insensitive per cogliere le varianti, ma "hume" minuscolo in
            # mezzo a una frase non e' il filosofo.
            if entry["cap"] and not surface[:1].isupper():
                return surface
            node = entry["id"]
            if node in linked:
                return surface
            linked.add(node)
            count += 1
            # L'etichetta e' il testo cosi' com'e' nella fonte: la prosa non
            # cambia, si aggiunge solo il collegamento.
            return f"[[{node}|{surface}]]"

        return pat.sub(one, chunk)

    return "\n".join(sub_line(l) for l in body.split("\n")), count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="misura e salva le frequenze")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    paths = atom_paths()

    if args.report or not os.path.exists(DOCFREQ):
        surf, freq = report(paths)
        os.makedirs(os.path.dirname(DOCFREQ), exist_ok=True)
        with open(DOCFREQ, "w", encoding="utf-8") as fh:
            json.dump({"n_docs": len(paths), "doc_freq": freq}, fh, ensure_ascii=False, indent=1)
        print(f"frequenze salvate: {DOCFREQ} ({len(paths)} atomi, {len(freq)} superfici viste)")
        if args.report:
            rows = sorted(freq.items(), key=lambda kv: -kv[1])
            print("\n--- superfici piu' diffuse ---")
            for s, c in rows[:20]:
                pct = 100.0 * c / len(paths)
                print(f"{c:6d} ({pct:5.1f}%)  {s!r}")
            return 0

    with open(DOCFREQ, encoding="utf-8") as fh:
        d = json.load(fh)
    n_docs, freq = d["n_docs"], d["doc_freq"]

    tax = load_taxonomy()
    table = linkable_surfaces(freq, tax, n_docs=n_docs)
    dropped = len(all_surfaces(tax)) - len(table)
    print(f"{len(table)} superfici linkabili ({dropped} scartate: generiche o ambigue)")

    pat = surface_pattern(list(table))
    if pat is None:
        print("nessuna superficie linkabile")
        return 1

    touched = total = 0
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            raw = fh.read()
        fm, body = split_fm(raw)
        if WIKILINK_RE.search(body):
            continue  # gia' linkato: il passaggio e' idempotente
        new_body, n = link_body(body, table, pat)
        if n == 0:
            continue
        touched += 1
        total += n
        if not args.dry_run:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(fm + new_body)

    verb = "linkerebbe" if args.dry_run else "linkati"
    print(f"{verb}: {total} wikilink in {touched}/{len(paths)} atomi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
