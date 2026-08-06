"""Spezza un digest troppo grande in blocchi taggabili da un agente solo.

Ortega ha 722 opere e un digest da 2,6 MB: non entra in una finestra. Si taglia
per opere intere (mai a meta' di un'opera: il tagger giudica l'opera, non il
byte) e si bilancia sui byte, non sul conteggio — le opere di Ortega vanno da 30
parole a un volume intero.

    python scripts/split_digest.py "Ortega y Gasset" --max-bytes 300000

Emette data/digests/chunks/<Nome>.partNN.md e stampa il piano.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIG = ROOT / "data" / "digests"
OUT = DIG / "chunks"
SEP = "===== OPERA:"


def works(text: str) -> list[str]:
    """I blocchi-opera, ciascuno completo di intestazione."""
    parts = text.split("\n" + SEP)
    head = parts[0]
    out = [head] if head.startswith(SEP) else []
    out += [SEP + p for p in parts[1:]]
    return [w for w in out if w.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("philosopher")
    ap.add_argument("--max-bytes", type=int, default=300_000)
    a = ap.parse_args()

    src = DIG / f"{a.philosopher}.md"
    if not src.is_file():
        print(f"ERRORE: {src} non esiste")
        return 1
    ws = works(src.read_text(encoding="utf-8"))
    if not ws:
        print("ERRORE: nessuna opera trovata (separatore cambiato?)")
        return 1

    chunks: list[list[str]] = []
    cur: list[str] = []
    n = 0
    for w in ws:
        b = len(w.encode("utf-8"))
        # Un'opera piu' grande del limite finisce da sola nel suo blocco: meglio
        # un blocco fuori misura che un'opera tagliata a meta'.
        if cur and n + b > a.max_bytes:
            chunks.append(cur)
            cur, n = [w], b
        else:
            cur.append(w)
            n += b
    if cur:
        chunks.append(cur)

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob(f"{a.philosopher}.part*.md"):
        old.unlink()
    print(f"{len(ws)} opere -> {len(chunks)} blocchi")
    for i, c in enumerate(chunks, 1):
        p = OUT / f"{a.philosopher}.part{i:02d}.md"
        p.write_text("\n".join(c), encoding="utf-8")
        print(f"  {p.name}: {len(c):3} opere  {p.stat().st_size // 1024:4} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
