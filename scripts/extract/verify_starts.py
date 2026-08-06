"""Verifica la passata: ogni first_line deve esistere DAVVERO nel corpo."""
import json, sys
from pathlib import Path
from scripts.extract.common import load_raw
from scripts.extract.delphi_body import body_search_start, find_body_line, strip_to_start
from scripts.extract.delphi_toc import parse_toc
from scripts.extract.sources import delphi_sources

STARTS_PATH = Path(__file__).resolve().parents[2] / "data" / "work_starts.json"
starts_all = json.loads(STARTS_PATH.read_text(encoding="utf-8"))
tot_ok = tot_bad = tot_skip = 0
for s in delphi_sources():
    starts = starts_all.get(s.key, {})
    text = load_raw(s); lines = text.split("\n")
    entries = parse_toc(text); titles = [e.title for e in entries]
    works = [e for e in entries if e.kind == "work"]
    pos = body_search_start(lines); loc = []
    for e in entries:
        i = find_body_line(lines, e.title, pos, titles)
        if i is None: continue
        loc.append((i, e)); pos = i + 1
    ok = bad = skip = 0; misses = []
    for n, (idx, e) in enumerate(loc):
        if e.kind != "work": continue
        info = starts.get(e.title)
        if info is None:
            bad += 1; misses.append((e.title, "ASSENTE dal json")); continue
        if info.get("skip"): skip += 1; continue
        end = loc[n+1][0] if n+1 < len(loc) else len(lines)
        body = "\n".join(lines[idx+1:end])
        clean, found = strip_to_start(body, info.get("first_line", ""))
        if not found:
            bad += 1
            misses.append((e.title, "first_line NON trovata: %r" % info.get("first_line","")[:40]))
        elif not clean.strip():
            bad += 1; misses.append((e.title, "testo VUOTO dopo il taglio"))
        else:
            ok += 1
    mark = "OK  " if bad == 0 else "FAIL"
    print(f"{mark} {s.key:10} {ok:2} pubblicabili, {skip} skip  (TOC ne dava {len(works)})")
    for t, why in misses[:4]: print(f"       {t[:38]:40} {why}")
    tot_ok += ok; tot_bad += bad; tot_skip += skip
print(f"\nPUBBLICABILI: {tot_ok} | skip: {tot_skip} | FALLITE: {tot_bad}")
sys.exit(1 if tot_bad else 0)
