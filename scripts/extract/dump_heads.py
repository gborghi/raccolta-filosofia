# scripts/extract/dump_heads.py
"""Estrae le teste delle opere per la passata di lettura.

Deterministico: nessun LLM qui. L'output di questo script è ciò che i subagent
della sessione Claude Code leggono per produrre data/work_starts.json.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .common import load_raw
from .delphi_body import body_search_start, find_body_line
from .delphi_toc import parse_toc
from .sources import Source, delphi_sources

HEAD_MARKER = "===== OPERA:"
HEADS_DIR = Path(__file__).resolve().parents[2] / "data" / "heads"


def dump_heads(text: str, source: Source, lines_per_work: int = 45) -> str:
    lines = text.split("\n")
    entries = parse_toc(text)
    titles = [e.title for e in entries]
    out: list[str] = []
    pos = body_search_start(lines)
    for e in entries:
        idx = find_body_line(lines, e.title, pos, titles)
        if idx is None:
            continue
        pos = idx + 1
        if e.kind != "work":
            continue
        head = lines[idx + 1: idx + 1 + lines_per_work]
        out.append(f"{HEAD_MARKER} {e.title}")
        out.extend(head)
        out.append("")
    return "\n".join(out)


def main() -> int:
    HEADS_DIR.mkdir(parents=True, exist_ok=True)
    for s in delphi_sources():
        text = load_raw(s)
        path = HEADS_DIR / f"{s.key}.md"
        path.write_text(dump_heads(text, s), encoding="utf-8")
        print(f"{s.key}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
