#!/usr/bin/env python3
"""Ripulisce i wikilink inventati dalle traduzioni IT respinte da HY.

Legge rejected.jsonl, per ogni atomo con "wikilink inventati" o "wikilink
senza etichetta":
  - carica il file .it.md
  - estrae tutti i [[TARGET|label]] o [[TARGET]]
  - se TARGET non e' un ID valido del vocabolario, rimuove le quadre
    (lascia il testo dell'etichetta)
  - riscrive il file

Non tocca gli atomi con "blocchi" o "eccezione" (pochi, da gestire a mano).
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # quartz-philosophy/ (da scripts/translate/)
VAULT = ROOT.parents[1] / "VaultPhilosophy"  # risale a Philosophy/ -> VaultPhilosophy/
TAXONOMY_PATH = ROOT / "data" / "taxonomy.json"
REJECTED_PATH = ROOT / "scripts" / "translate" / "run_logs" / "rejected.jsonl"

LINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")


def load_taxonomy_ids(path: Path) -> set[str]:
    tax = json.loads(path.read_text(encoding="utf-8"))
    ids: set[str] = set()
    for key in ("axes", "positions", "concepts", "figures", "schools", "forms", "arguments"):
        for item in tax.get(key, []):
            if isinstance(item, dict) and "id" in item:
                ids.add(item["id"])
    return ids


def fix_links(text: str, valid_ids: set[str]) -> tuple[str, int]:
    """Rimuove i wikilink il cui target non e' nel vocabolario. Restituisce
    (testo_fixato, numero_link_rimossi)."""
    removed = 0

    def repl(m: re.Match) -> str:
        nonlocal removed
        target = m.group(1)
        label = m.group(2) if m.group(2) is not None else target
        if target not in valid_ids:
            removed += 1
            return label  # solo il testo, senza quadre
        return m.group(0)  # link valido, lo tiene

    fixed = LINK_RE.sub(repl, text)
    return fixed, removed


def process_rejected(valid_ids: set[str], dry_run: bool = False) -> dict:
    """Processa rejected.jsonl e ripara i wikilink inventati."""
    if not REJECTED_PATH.exists():
        print(f"File non trovato: {REJECTED_PATH}")
        return {}

    lines = REJECTED_PATH.read_text(encoding="utf-8").strip().splitlines()
    stats = {"fixed": 0, "skipped": 0, "errors": 0, "total_removed": 0}

    for line in lines:
        rec = json.loads(line)
        atom_rel = rec.get("atom", "")
        lang = rec.get("lang", "")
        problems = rec.get("problems", [])

        # Interessano solo IT con wikilink inventati
        if lang != "it":
            stats["skipped"] += 1
            continue

        has_inventati = any("wikilink inventati" in p for p in problems)
        has_senza = any("wikilink senza etichetta" in p for p in problems)
        if not (has_inventati or has_senza):
            stats["skipped"] += 1
            continue

        # Percorso del file tradotto
        atom_path = VAULT / atom_rel
        it_path = atom_path.with_suffix(".it.md")
        if not it_path.exists():
            print(f"  NON TROVATO: {it_path}")
            stats["errors"] += 1
            continue

        text = it_path.read_text(encoding="utf-8")
        fixed, removed = fix_links(text, valid_ids)

        if removed > 0:
            if not dry_run:
                it_path.write_text(fixed, encoding="utf-8")
            short = atom_rel.split("Atomized/")[-1] if "Atomized/" in atom_rel else atom_rel
            print(f"  OK {short}: rimossi {removed} wikilink inventati")
            stats["fixed"] += 1
            stats["total_removed"] += removed
        else:
            stats["skipped"] += 1

    return stats


def main():
    dry_run = "--dry-run" in sys.argv
    print("Carico vocabolario...")
    valid_ids = load_taxonomy_ids(TAXONOMY_PATH)
    print(f"  {len(valid_ids)} ID validi nel vocabolario")

    print(f"\nProcesso rejected.jsonl {'(dry-run)' if dry_run else ''}...")
    stats = process_rejected(valid_ids, dry_run=dry_run)

    print(f"\nRiepilogo:")
    print(f"  riparati:  {stats['fixed']}")
    print(f"  saltati:   {stats['skipped']}")
    print(f"  errori:    {stats['errors']}")
    print(f"  tot link rimossi: {stats['total_removed']}")

    if dry_run:
        print("\nDry-run: nessun file modificato. Rimuovi --dry-run per applicare.")


if __name__ == "__main__":
    main()
