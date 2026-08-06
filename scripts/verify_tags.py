"""Verifica la passata di tagging.

Il modo in cui questa passata fallisce in silenzio e' un ID inventato: il tag
sembra plausibile, il grafo lo accetta, e il link non porta da nessuna parte.
Qui ogni ID emesso deve esistere in taxonomy.json.
"""
from __future__ import annotations
import json, re, sys, unicodedata
from pathlib import Path

# macOS/Dropbox restituisce i nomi file in NFD (é = e + accento combinante),
# mentre le chiavi del json di tag sono in NFC (é precomposto): senza
# normalizzare, ogni opera dal titolo accentato risulterebbe insieme "mancante
# dal json" e "inesistente", un falso allarme che nasconderebbe quelli veri.
def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)

ROOT = Path(__file__).resolve().parents[1]
TAX = json.loads((ROOT / "data" / "taxonomy.json").read_text(encoding="utf-8"))
KINDS = {"axes": "axes", "positions": "positions", "concepts": "concepts",
         "arguments": "arguments", "figures": "figures", "forms": "forms",
         "schools": "schools"}
VALID = {k: {n["id"] for n in TAX[v]} for k, v in KINDS.items()}
POS = {p["id"]: p for p in TAX["positions"]}

def works_of(ph: str) -> set[str]:
    d = ROOT.parent / "VaultPhilosophy" / "Philosophers" / ph / "_raw"  # vault fratello di quartz-philosophy/
    return {_nfc(p.stem) for p in d.glob("*.md")} if d.is_dir() else set()

def main() -> int:
    tags_dir = ROOT / "data" / "tags"
    bad = 0; total_w = 0; counts = {k: 0 for k in KINDS}
    for f in sorted(tags_dir.glob("*.json")):
        ph = f.stem
        d = json.loads(f.read_text(encoding="utf-8"))
        expect = works_of(ph)
        keys = {_nfc(k) for k in d}
        missing = expect - keys
        extra = keys - expect
        errs = []
        for w, t in d.items():
            total_w += 1
            for k in KINDS:
                for v in t.get(k, []):
                    counts[k] += 1
                    if v not in VALID[k]:
                        errs.append(f"{w}: {k} -> ID INESISTENTE {v!r}")
            # NOTA: una posizione attraversa gli assi (lo scetticismo sulla
            # conoscenza e quello su Dio sono la stessa mossa su domande diverse).
            # L'asse della posizione viene DERIVATO da build_graph, non preteso qui.
            if not t.get("summary_it") or not t.get("summary_en"):
                errs.append(f"{w}: summary bilingue mancante")
        ok = not (errs or missing)
        print(f"{'OK  ' if ok else 'FAIL'} {ph:10} {len(d):2}/{len(expect):2} opere")
        for m in sorted(missing)[:3]: print(f"       MANCA dal json: {m}")
        for e in sorted(extra)[:3]:  print(f"       opera inesistente: {e}")
        for e in errs[:5]: print(f"       {e}")
        if not ok: bad += 1
    print(f"\nopere taggate: {total_w}")
    print("tag emessi: " + " ".join(f"{k}={v}" for k, v in counts.items()))
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
