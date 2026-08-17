#!/usr/bin/env python3
"""Rileva e traduce con qwen-mt-turbo gli atomi senza traduzione necessaria.

Uso:
    # 1) Scan + stats (dry-run)
    python scripts/translate/fix_missing_translations.py --vault PATH --dry-run

    # 2) Translate missing
    python scripts/translate/fix_missing_translations.py --vault PATH [--force]

Logica (REGOLE.md):
  fonte en   -> serve .it.md
  fonte it   -> serve .en.md
  altra      -> servono .en.md e .it.md

Frontmatter minimo: philosopher, lang, work, atom_n (copiati dalla fonte).
Resume automatico in data/ds_translate_resume.jsonl — non perde progresso.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

ICT_QWEN = Path("/Users/g.borghi/Library/CloudStorage/Dropbox/insegnamento/ICT/qwen/api_key")

DASHSCOPE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
_resume_log_path = None


def _read_api_key() -> str:
    for src in (
        os.environ.get("QWEN_API_KEY"),
        os.environ.get("DASHSCOPE_API_KEY"),
        str(Path.home() / ".config" / "qwen" / "api_key"),
        str(ICT_QWEN),
    ):
        if src and Path(src).is_file():
            val = Path(src).read_text(encoding="utf-8").strip()
            if val:
                return val
    raise SystemExit(
        "Nessuna API key trovata.\n"
        "  $QWEN_API_KEY / $DASHSCOPE_API_KEY\n"
        f"  ~/.config/qwen/api_key\n"
        f"  ICT/qwen/api_key\n"
        "Crea una chiave su https://dashscope.console.aliyun.com/"
    )


def _http_json(payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        DASHSCOPE_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _translate(text: str, source_lang: str, target_lang: str) -> str:
    """Translate text using qwen-mt-turbo with shortest working prompt."""
    # Keep it ultra-short: qwen-mt-turbo only respects the LAST line before the text
    if target_lang == "it":
        header = "Traduci in italiano."
    else:
        header = "Translate to English."
    prompt = header + "\n\n" + text
    messages = [{"role": "user", "content": prompt}]
    payload = {
        "model": "qwen-mt-turbo",
        "messages": messages,
        "temperature": 0,
        "max_tokens": 8192,
    }
    try:
        resp = _http_json(payload, timeout=600)
        content = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
        usage = resp.get("usage", {})
        print(
            f"  [{resp.get('model','mt-turbo')}] "
            f"tokens: prompt={usage.get('prompt_tokens','?')} "
            f"completion={usage.get('completion_tokens','?')}",
            file=sys.stderr,
        )
        return content.strip() if content else ""
    except Exception as e:
        raise


# ---------- parsing ----------

FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.S)


def _parse_fm(raw: str):
    m = FM_RE.match(raw)
    if not m:
        return {}, raw
    fm = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, raw[m.end():]


REQUIRED_MAP = {"en": ["it"], "it": ["en"]}
OTHER_NEEDS = ["en", "it"]


def _atom_id(fm):
    return f'{fm.get("philosopher","?")}/{fm.get("work","?")}/{fm.get("atom_n","?")}'


def _write_tr(src_path, fm, body, lang):
    tr = src_path.with_suffix(f".{lang}.md")
    lines = [
        "---",
        f'philosopher: "{fm.get("philosopher","?")}"',
        f'lang: "{lang}"',
        f'work: "{fm.get("work","?")}"',
        f'atom_n: "{fm.get("atom_n","?")}"',
        "---",
        "",
        body,
        "",
    ]
    tr.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Colma traduzioni mancanti con qwen-mt-turbo.")
    ap.add_argument("--vault", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.3)
    args = ap.parse_args()

    vault = Path(args.vault) if args.vault else Path(__file__).resolve().parents[3] / "VaultPhilosophy"
    if not vault.is_dir():
        raise SystemExit(f"Vault non trovato: {vault}")

    global _key, _resume_log_path
    _key = _read_api_key()

    # Resume log in data/
    _resume_log_path = vault.parent / "data" / "ds_translate_resume.jsonl"
    _resume_log_path.parent.mkdir(parents=True, exist_ok=True)

    # Load resumed keys
    processed_keys = set()
    if _resume_log_path.is_file():
        for line in _resume_log_path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                # Only "langs" records mark an atom as fully translated;
                # "lang"/error records are diagnostics and must not block retry.
                if "langs" in rec:
                    processed_keys.add(rec["key"])
            except (json.JSONDecodeError, KeyError):
                pass

    # ---- SCAN PHASE ----
    stats = defaultdict(lambda: {"total": 0, "missing_total": 0})

    def _scan_gen():
        """Generator that yields source atoms needing translation."""
        for root, _, names in os.walk(vault):
            for name in names:
                if not name.endswith(".md") or name.endswith((".it.md", ".en.md")):
                    continue
                src = Path(root) / name
                try:
                    raw = src.read_text(encoding="utf-8")
                except Exception:
                    continue
                fm, body = _parse_fm(raw)
                lang = fm.get("lang", "").lower()
                if not lang:
                    continue
                # Only atoms are published to the site; _raw ("kind: work") files
                # are out of scope and their `?/?` resume keys are false positives.
                if fm.get("kind") != "atom":
                    continue
                needed = REQUIRED_MAP.get(lang, OTHER_NEEDS)
                existing = [tl for tl in needed if src.with_suffix(f".{tl}.md").is_file()]
                missing = [tl for tl in needed if tl not in existing or args.force]
                if missing:
                    yield src, fm, body, needed, existing, missing

    total_atoms = 0
    total_missing = 0
    by_philosopher = defaultdict(int)
    skip_from_resume = 0

    for src, fm, body, needed, existing, missing in _scan_gen():
        aid = _atom_id(fm)
        total_atoms += 1
        n_missing = len(missing)
        total_missing += n_missing
        ph = fm.get("philosopher", "?")
        by_philosopher[ph] += n_missing

        if aid in processed_keys:
            skip_from_resume += 1

    # Print summary
    print("=" * 70, file=sys.stderr)
    print(f"VAULT: {vault}", file=sys.stderr)
    print(f"Total atoms with missing translations: {total_atoms}", file=sys.stderr)
    print(f"Total individual translations needed:  {total_missing}", file=sys.stderr)
    print(f"(Already processed via resume: {skip_from_resume})", file=sys.stderr)
    print("-" * 70, file=sys.stderr)
    print("Missing translations by philosopher:", file=sys.stderr)
    for ph in sorted(by_philosopher, key=by_philosopher.__getitem__, reverse=True):
        print(f"  {ph:30s}: {by_philosopher[ph]:>6}", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    if total_missing == 0:
        print("Nessuna traduzione mancante.", file=sys.stderr)
        return

    if args.dry_run:
        print("[dry-run] Nessun file verrà scritto.", file=sys.stderr)
        return

    # ---- TRANSLATE PHASE ----
    written = 0
    failed = 0
    idx = 0

    for src, fm, body, needed, existing, missing in _scan_gen():
        aid = _atom_id(fm)

        # Skip resumed
        if aid in processed_keys:
            continue

        atom_failed = False
        for target_lang in missing:
            idx += 1
            rel = src.relative_to(vault.parent)
            print(f"[{idx}] {rel} -> {target_lang} ", end="", file=sys.stderr)

            try:
                translated = _translate(body, fm.get("lang","").lower(), target_lang)
            except Exception as e:
                print(f"ERROR: {e}", file=sys.stderr)
                failed += 1
                atom_failed = True
                # Save error record for resume
                with open(_resume_log_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"key": aid, "lang": target_lang, "error": str(e)}) + "\n")
                continue

            if translated:
                _write_tr(src, fm, translated, target_lang)
                written += 1
                print(f"OK ({len(translated)} chars)", file=sys.stderr)
            else:
                print("EMPTY RESPONSE", file=sys.stderr)
                failed += 1
                atom_failed = True

            time.sleep(args.sleep)

        # Mark atom as fully processed only if every missing lang was written,
        # otherwise the next run re-queues just the still-missing langs.
        if not atom_failed:
            processed_keys.add(aid)
            with open(_resume_log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": aid, "langs": list(set(existing) | set(missing))}) + "\n")

    print(f"\nDone: written={written} skipped(resumed)={skip_from_resume} failed={failed}")


if __name__ == "__main__":
    main()
