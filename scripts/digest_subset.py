"""Digest ristretto a un elenco di opere, per le ripassate mirate.

    python scripts/digest_subset.py "Ortega y Gasset" data/ortega_blind.json out.md

Serve quando un difetto ha reso invisibile una parte del corpus e va ritaggata
solo quella: rifare l'intero filosofo costerebbe dieci volte tanto e
riscriverebbe tag buoni.

Fail-closed: se un nome dell'elenco non esiste nel digest, ci si ferma. Un
elenco che non combacia col digest e' un errore di partenza — proseguire
significherebbe ritaggare un sottoinsieme diverso da quello che si crede, e il
conteggio finale tornerebbe lo stesso.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEP = "===== OPERA:"


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 1
    ph, list_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

    src = ROOT / "data" / "digests" / f"{ph}.md"
    text = src.read_text(encoding="utf-8")
    blocks: dict[str, str] = {}
    for b in text.split("\n" + SEP)[1:] if not text.startswith(SEP) else text.split(SEP)[1:]:
        stem = b.split("\n")[0].strip()
        blocks[stem] = SEP + b

    wanted = json.loads(Path(list_path).read_text(encoding="utf-8"))
    if isinstance(wanted, dict):
        wanted = wanted.get(ph, [])

    missing = [w for w in wanted if w not in blocks]
    if missing:
        print(f"ERRORE: {len(missing)} nomi non presenti nel digest di {ph}:")
        for m in missing[:10]:
            print(f"  - {m}")
        return 1

    out = "\n".join(blocks[w] for w in wanted)
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(out, encoding="utf-8")
    print(f"{len(wanted)} opere -> {p} ({p.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
