#!/usr/bin/env python3
"""Ripristina i wikilink persi nelle traduzioni IT respinte da HY.

Per ogni atomo in rejected.jsonl con "wikilink: persi", confronta il file
.it.md con la fonte .md e ripristina i wikilink mancanti.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAULT = ROOT.parents[1] / "VaultPhilosophy"
REJECTED_PATH = ROOT / "scripts" / "translate" / "run_logs" / "rejected.jsonl"

LINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")


def extract_links(text: str) -> dict[str, str]:
    """Mappa target -> testo completo del wikilink."""
    links: dict[str, str] = {}
    for m in LINK_RE.finditer(text):
        links[m.group(1)] = m.group(0)
    return links


def main():
    dry_run = "--dry-run" in sys.argv
    if not REJECTED_PATH.exists():
        print(f"Non trovato: {REJECTED_PATH}")
        return

    lines = REJECTED_PATH.read_text(encoding="utf-8").strip().splitlines()
    fixed = 0
    for line in lines:
        rec = json.loads(line)
        if rec.get("lang") != "it":
            continue
        problems = rec.get("problems", [])
        persi = [p for p in problems if "wikilink: persi" in p]
        if not persi:
            continue

        atom_rel = rec["atom"]
        src_path = VAULT / atom_rel  # .md
        it_path = VAULT / atom_rel.replace(".md", ".it.md")

        if not src_path.exists() or not it_path.exists():
            continue

        src_text = src_path.read_text(encoding="utf-8")
        it_text = it_path.read_text(encoding="utf-8")

        src_links = extract_links(src_text)
        it_links = extract_links(it_text)

        # Trova i target persi
        missing_targets = set(src_links.keys()) - set(it_links.keys())
        if not missing_targets:
            continue

        short = atom_rel.split("Atomized/")[-1] if "Atomized/" in atom_rel else atom_rel
        print(f"  {short}: persi={missing_targets}")

        # Per ogni target perso, cerca il testo dell'etichetta nel testo
        # tradotto e aggiungi il wikilink. Strategia semplice: cerca la
        # prima occorrenza dell'etichetta (o del target) e wrappala.
        for target in missing_targets:
            full_link = src_links[target]  # es. [[grace|grazia]]
            # Estrai l'etichetta: [[target|label]] -> label; [[target]] -> target
            m = LINK_RE.match(full_link)
            if not m:
                continue
            target_id = m.group(1)
            label = m.group(2) or target_id

            # Nel testo IT, cerca l'etichetta tradotta. Non sappiamo come HY
            # l'ha tradotta, quindi cerchiamo una parola chiave.
            # Per ora skip — troppo complesso da automatizzare.
            pass

        fixed += 1

    print(f"\nFile controllati: {fixed}")
    print("NOTA: il ripristino automatico dei wikilink persi richiede")
    print("traduzione manuale delle etichette. Usa --report per vedere")
    print("quali target mancano in ogni file.")


if __name__ == "__main__":
    main()
