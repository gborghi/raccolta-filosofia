#!/usr/bin/env python3
"""Retry mirato per i 17 atomi rimasti senza traduzione (falliti con HTTP 400).

Due cause distinte, verificate via probe:
  - 7 Hegel (en->it, 3.7-8.9KB): il filtro contenuti di DashScope blocca
    l'output di qwen-mt-turbo (`data_inspection_failed`). Si usa qwen3.7-flash
    in un'unica chiamata, che sul medesimo input risponde OK.
  - 10 Spinoza (la->en e la->it, 28-50KB): errore di input length
    (`[1, 8192]`). Si spezza il corpo in chunk di <=6000 caratteri (i paragrafi
    reali sono <=4555) e si traduce ogni chunk con qwen-mt-turbo, ricongiungendo
    con \n\n.

Scrive i sibling (foo.it.md / foo.en.md / foo.la.en.md / foo.la.it.md) con il
frontmatter minimo di fix_missing_translations.py e aggiorna
data/ds_translate_resume.jsonl con i record `{"key","langs"}`.
"""

import json
import re
import sys
import time
from pathlib import Path

import fix_missing_translations as base

VAULT = Path(__file__).resolve().parents[3] / "VaultPhilosophy"
RESUME = VAULT.parent / "data" / "ds_translate_resume.jsonl"
FLASH = "qwen3.7-flash"
CHUNK_LIMIT = 6000
SLEEP = 0.5

# (relpath dal vault, sorgente presente) — tutti con frontmatter kind: "atom"
TARGETS = [
    "Philosophers/Hegel/Atomized/Lectures_on_the_History_of_Philosophy/189_3_Philosophy_of_Mind.md",
    "Philosophers/Hegel/Atomized/Lectures_on_the_History_of_Philosophy/294_5_The_Successors_of_Proclus.md",
    "Philosophers/Hegel/Atomized/Lectures_on_the_Proofs_of_the_Existence_of_God/008_THIRD_LECTURE.md",
    "Philosophers/Hegel/Atomized/The_Logic_of_Hegel/031_V_Third_Attitude_of_Thought_to_Objectivi.md",
    "Philosophers/Hegel/Atomized/The_Philosophy_of_History/055_SECTION_II_INDIA.md",
    "Philosophers/Hegel/Atomized/The_Philosophy_of_History/057_SECTION_II_INDIA.md",
    "Philosophers/Hegel/Atomized/The_Philosophy_of_History/147_Chapter_II_The_Crusades.md",
    "Philosophers/Spinoza/Atomized/Ethics/147_PROP_LIX_Among_all_the_emotions_attribut.la.md",
    "Philosophers/Spinoza/Atomized/Political_Treatise/008_Chapter_VII.la.md",
    "Philosophers/Spinoza/Atomized/Political_Treatise/009_Chapter_VIII.la.md",
    "Philosophers/Spinoza/Atomized/Theological-Political_Treatise/002_CHAPTER_I.la.md",
    "Philosophers/Spinoza/Atomized/Theological-Political_Treatise/003_CHAPTER_II.la.md",
    "Philosophers/Spinoza/Atomized/Theological-Political_Treatise/004_CHAPTER_III.la.md",
    "Philosophers/Spinoza/Atomized/Theological-Political_Treatise/007_CHAPTER_VI.la.md",
    "Philosophers/Spinoza/Atomized/Theological-Political_Treatise/008_CHAPTER_VII.la.md",
    "Philosophers/Spinoza/Atomized/Theological-Political_Treatise/010_CHAPTER_IX.la.md",
    "Philosophers/Spinoza/Atomized/Theological-Political_Treatise/018_CHAPTER_XVII.la.md",
]


def _split_piece(p: str, limit: int):
    """Riduce un singolo paragrafo oltre `limit`: prima per righe, poi a tratti."""
    if len(p) <= limit:
        return [p]
    parts = p.split("\n")
    res, cur = [], ""
    for part in parts:
        if len(part) > limit:
            if cur:
                res.append(cur)
                cur = ""
            for i in range(0, len(part), limit):
                res.append(part[i : i + limit])
        else:
            cand = cur + "\n" + part if cur else part
            if len(cand) <= limit:
                cur = cand
            else:
                res.append(cur)
                cur = part
    if cur:
        res.append(cur)
    return res


def _chunks(text: str, limit: int = CHUNK_LIMIT):
    """Raggruppa i paragrafi in chunk di <= limit caratteri, separati da \\n\\n."""
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        for piece in _split_piece(para, limit):
            if not piece:
                continue
            cand = cur + "\n\n" + piece if cur else piece
            if len(cand) <= limit:
                cur = cand
            else:
                if cur:
                    chunks.append(cur)
                cur = piece
    if cur:
        chunks.append(cur)
    return chunks


def _translate(model: str, text: str, target_lang: str) -> str:
    header = "Traduci in italiano." if target_lang == "it" else "Translate to English."
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": header + "\n\n" + text}],
        "temperature": 0,
        "max_tokens": 8192,
    }
    resp = base._http_json(payload, timeout=600)
    content = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return content.strip() if content else ""


def _translate_chunked(body: str, target_lang: str) -> str:
    parts = [_translate("qwen-mt-turbo", c, target_lang) for c in _chunks(body)]
    return "\n\n".join(parts)


def main():
    base._key = base._read_api_key()
    RESUME.parent.mkdir(parents=True, exist_ok=True)

    processed = set()
    if RESUME.is_file():
        for line in RESUME.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                if "langs" in rec:
                    processed.add(rec["key"])
            except (json.JSONDecodeError, KeyError):
                pass

    ok, failed = 0, 0
    for rel in TARGETS:
        src = VAULT / rel
        if not src.is_file():
            print(f"[skip] manca il sorgente: {rel}", file=sys.stderr)
            continue
        raw = src.read_text(encoding="utf-8")
        fm, body = base._parse_fm(raw)
        aid = base._atom_id(fm)
        lang = fm.get("lang", "").lower()
        needed = base.REQUIRED_MAP.get(lang, base.OTHER_NEEDS)
        missing = [
            tl
            for tl in needed
            if not src.with_suffix(f".{tl}.md").is_file() and tl not in processed
        ]

        if aid in processed:
            print(f"[skip] {aid} gia' in resume", file=sys.stderr)
            continue
        if not missing:
            print(f"[skip] {aid} gia' completo", file=sys.stderr)
            continue

        print(f"[go] {aid} -> {missing}", file=sys.stderr)
        atom_failed = False
        for tl in missing:
            print(f"  {tl} ...", end=" ", file=sys.stderr)
            try:
                if lang == "en":
                    translated = _translate(FLASH, body, tl)
                else:
                    translated = _translate_chunked(body, tl)
            except Exception as e:
                print(f"ERROR {e}", file=sys.stderr)
                with open(RESUME, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"key": aid, "lang": tl, "error": str(e)}) + "\n")
                failed += 1
                atom_failed = True
                continue
            if not translated:
                print("EMPTY", file=sys.stderr)
                failed += 1
                atom_failed = True
                continue
            base._write_tr(src, fm, translated, tl)
            print(f"OK ({len(translated)} chars)", file=sys.stderr)
            ok += 1
            time.sleep(SLEEP)

        if not atom_failed:
            with open(RESUME, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": aid, "langs": needed}) + "\n")

    print(f"\nDone: written={ok} failed={failed}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
