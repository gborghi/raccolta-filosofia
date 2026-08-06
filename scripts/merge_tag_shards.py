"""Fonde data/tags/_shards/<Nome>.partNN.json in data/tags/<Nome>.json.

Dieci agenti sullo stesso file JSON si sovrascrivono a vicenda in silenzio: chi
scrive per ultimo vince e gli altri nove blocchi spariscono senza un errore.
Percio' ciascuno scrive il proprio shard e la fusione avviene qui, una volta
sola, con i controlli che l'ultimo-che-scrive non farebbe mai:

- un'opera presente in due shard e' un errore di partizione, non un merge da
  risolvere scegliendo: ci si ferma.
- il totale finale deve coprire tutte le opere in _raw. Un buco qui e' esattamente
  il difetto che il merge ingenuo nasconderebbe.

    python scripts/merge_tag_shards.py "Ortega y Gasset"
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAGS = ROOT / "data" / "tags"
SHARDS = TAGS / "_shards"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("philosopher")
    a = ap.parse_args()

    parts = sorted(SHARDS.glob(f"{a.philosopher}.part*.json"))
    if not parts:
        print(f"ERRORE: nessuno shard per {a.philosopher}")
        return 1

    out: dict = {}
    for p in parts:
        d = json.loads(p.read_text(encoding="utf-8"))
        dup = set(d) & set(out)
        if dup:
            print(f"ERRORE: {p.name} ridefinisce {len(dup)} opere gia' presenti")
            for w in sorted(dup)[:5]:
                print(f"  - {w}")
            return 1
        out.update(d)
        print(f"  {p.name}: +{len(d)} opere")

    raw = ROOT.parent / "VaultPhilosophy" / "Philosophers" / a.philosopher / "_raw"  # vault fratello di quartz-philosophy/
    expect = {f.stem for f in raw.glob("*.md")}
    missing = expect - set(out)
    extra = set(out) - expect

    dest = TAGS / f"{a.philosopher}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\nscritto {dest.name}: {len(out)}/{len(expect)} opere")
    if missing:
        print(f"MANCANO {len(missing)}: " + ", ".join(sorted(missing)[:5]))
    if extra:
        print(f"INESISTENTI {len(extra)}: " + ", ".join(sorted(extra)[:5]))
    return 1 if (missing or extra) else 0


if __name__ == "__main__":
    sys.exit(main())
