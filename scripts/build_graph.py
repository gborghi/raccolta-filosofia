"""Costruisce le note aggregatore del Knowledge Graph dai tag.

Un nodo aggregatore ha un ID canonico ed etichette bilingui; i wikilink
puntano all'ID, mai all'etichetta. E' cio' che rende il grafo indipendente
dalla lingua della fonte: un brano tedesco si raggiunge da una query inglese
perche' porta l'ID, non perche' contenga le parole.
"""
from __future__ import annotations
import json, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KG = ROOT.parent / "VaultPhilosophy" / "Knowledge Graph"  # il vault e' fratello di quartz-philosophy/
TAX = json.loads((ROOT / "data" / "taxonomy.json").read_text(encoding="utf-8"))

DIRS = {"axes": "Axes", "positions": "Positions", "concepts": "Concepts",
        "arguments": "Arguments", "figures": "Figures", "forms": "Forms",
        "schools": "Schools"}
SING = {"axes": "axis", "positions": "position", "concepts": "concept",
        "arguments": "argument", "figures": "figure", "forms": "form",
        "schools": "school"}

def esc(s): return str(s).replace("\\", "\\\\").replace('"', '\\"')

def load_tags():
    out = {}
    for f in sorted((ROOT / "data" / "tags").glob("*.json")):
        for w, t in json.loads(f.read_text(encoding="utf-8")).items():
            out[(f.stem, w)] = t
    return out

def main() -> int:
    tags = load_tags()
    if not tags:
        print("nessun tag: la passata non e' finita"); return 1

    # indice inverso: nodo -> opere.
    # L'asse di una posizione e' DERIVATO: taggare una posizione implica
    # l'asse su cui sta. Cosi' il tagger non deve ripeterlo, e una posizione
    # che attraversa piu' assi (scepticism su knowledge_origin e su god)
    # non va persa.
    POSAX = {p["id"]: p["axis"] for p in TAX["positions"]}
    VARIANTE = {p["id"]: p.get("variante_di") for p in TAX["positions"]
                if p.get("variante_di")}
    ARGAX = {a["id"]: (a["axis"], a["position"]) for a in TAX["arguments"]}
    back = defaultdict(list)
    for (ph, w), t in tags.items():
        axes = set(t.get("axes", []))
        for p in t.get("positions", []):
            if p in POSAX: axes.add(POSAX[p])
        for a in t.get("arguments", []):
            if a in ARGAX:
                axes.add(ARGAX[a][0])
        # Una FAMIGLIA assorbe le sue sfumature: taggare `empiricism_sceptical`
        # deve far comparire l'opera anche sotto `empiricism`, altrimenti la
        # pagina della famiglia e' vuota e i due livelli non servono a niente.
        positions = set(t.get("positions", []))
        for p in list(positions):
            fam = VARIANTE.get(p)
            while fam:
                positions.add(fam)
                axes.add(POSAX.get(fam, ""))
                fam = VARIANTE.get(fam)
        axes.discard("")
        for k in DIRS:
            if k == "axes":      vals = sorted(axes)
            elif k == "positions": vals = sorted(positions)
            else:                vals = t.get(k, [])
            for v in vals:
                back[v].append((ph, w))

    node = {n["id"]: (k, n) for k in DIRS for n in TAX[k]}
    written = 0
    for k, dirname in DIRS.items():
        d = KG / dirname
        d.mkdir(parents=True, exist_ok=True)
        for n in TAX[k]:
            nid = n["id"]
            works = sorted(back.get(nid, []))
            fm = ["---", f'id: "{nid}"', f'type: "{SING[k]}"',
                  f'label_it: "{esc(n["label_it"])}"', f'label_en: "{esc(n["label_en"])}"']
            if n.get("aliases"):
                fm.append("aliases:")
                fm += [f'  - "{esc(a)}"' for a in n["aliases"]]
            if k == "axes":
                fm.append("positions:")
                fm += [f'  - "{p}"' for p in n["positions"]]
            if k == "positions":
                fm.append(f'axis: "{n["axis"]}"')
                if n.get("variante_di"): fm.append(f'variante_di: "{n["variante_di"]}"')
                if n.get("contro"):
                    fm.append("contro:")
                    fm += [f'  - "{c}"' for c in n["contro"]]
            if k == "arguments":
                fm += [f'philosopher: "{n["philosopher"]}"', f'axis: "{n["axis"]}"',
                       f'position: "{n["position"]}"']
            fm += [f"work_count: {len(works)}", f'tags:\n  - graph/{SING[k]}', "---", ""]

            body = [f'# {n["label_it"]}', "", f'*{n["label_en"]}*', ""]
            if k == "axes":
                body += [f'> {n["question_it"]}', f'> *{n["question_en"]}*', "",
                         "## Posizioni su questo asse", ""]
                for pid in n["positions"]:
                    p = next((x for x in TAX["positions"] if x["id"] == pid), None)
                    if not p: continue
                    nw = len(back.get(pid, []))
                    contro = ", ".join(f"[[{c}]]" for c in p.get("contro", []))
                    body.append(f'- [[{pid}|{p["label_it"]}]] — {nw} opere'
                                + (f" · contro {contro}" if contro else ""))
                body.append("")
            if k == "positions":
                ax = next((a for a in TAX["axes"] if a["id"] == n["axis"]), None)
                if ax: body += [f'Posizione sull\'asse [[{ax["id"]}|{ax["label_it"]}]].', ""]
                if n.get("variante_di"): body += [f'Sfumatura di [[{n["variante_di"]}]].', ""]
                if n.get("contro"):
                    body += ["**Contro:** " + ", ".join(f"[[{c}]]" for c in n["contro"]), ""]
            if k == "arguments":
                body += [f'Argomento di **{n["philosopher"]}**. '
                         f'Asse [[{n["axis"]}]] · posizione [[{n["position"]}]].', ""]

            body += [f"## Opere ({len(works)})", ""]
            byph = defaultdict(list)
            for ph, w in works: byph[ph].append(w)
            for ph in sorted(byph):
                body.append(f"**{ph}**")
                body += [f"- [[{w}]]" for w in sorted(byph[ph])]
                body.append("")
            (d / f"{nid}.md").write_text("\n".join(fm + body), encoding="utf-8")
            written += 1
    print(f"note aggregatore scritte: {written}")
    for k, dirname in DIRS.items():
        used = sum(1 for n in TAX[k] if back.get(n["id"]))
        print(f"  {dirname:10} {len(TAX[k]):3} nodi, {used:3} usati da almeno un'opera")
    orphan = [nid for nid in node if not back.get(nid)]
    print(f"\nnodi orfani (nessuna opera): {len(orphan)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
