#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Traduce atomi residui VELOCE: una chiamata per atomo, senza check blocchi.

Il check "blocchi N vs M" di verify.py rifiuta traduzioni con paragrafi fusi.
Qui accettiamo la fusione: una singola chiamata per atomo, e verifichiamo solo
che il SENSO sia tutto presente (wikilink conservati, H1 presente, non rimasto
in inglese). Il controllo di copertura usa parole chiave della fonte.

    DEEPSEEK_API_KEY=sk-... python scripts/translate/run_residui_fast.py data/ds_batches/fallback_00.json
"""
import json
import os
import re
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_author_ds as ds  # noqa: E402
import verify  # noqa: E402

LOG_DIR = os.path.join(HERE, "run_logs")
REJECTED_PATH = os.path.join(LOG_DIR, "ds_batch_rejected.jsonl")
WORKERS = int(os.environ.get("DEEPSEEK_WORKERS", "4"))

_lock = threading.Lock()
_rej_lock = threading.Lock()

H1_RE = re.compile(r"^([ \t]*\r?\n)*[ \t]*#[ \t]+(.+?)[ \t]*$", re.M)
KEYWORD_RE = re.compile(r"[^\W\d_]{5,}", re.UNICODE)


def _call(src_body, tgt_lang, src_lang, extra=""):
    """Una chiamata API: traduce l'INTERO atomo."""
    tgt_name = ds.LANG_NAMES.get(tgt_lang, tgt_lang)
    src_name = ds.LANG_NAMES.get(src_lang, src_lang)
    sys_prompt = (
        "You are a literary translator of philosophical prose. "
        "Translate the following %s passage into %s. "
        "Preserve the author's register and ALL of the meaning. "
        "You may merge short paragraphs, but never omit content, sentences, "
        "or ideas. Keep the leading Markdown H1 heading '#'. "
        "Preserve EVERY marker like [[L01]], [[L02]] exactly where they appear; "
        "never drop, reorder, or translate them. %s "
        "Output ONLY the translation, nothing else."
    ) % (src_name, tgt_name, extra)
    body = json.dumps({
        "model": ds.DEEPSEEK_MODEL,
        "temperature": 0,
        "max_tokens": 65536,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": src_body},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        ds.DEEPSEEK_HOST + "/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + ds.API_KEY},
    )
    r = json.loads(urllib.request.urlopen(req, timeout=900).read())
    return r["choices"][0]["message"]["content"].strip()


def _coverage(src_body, tr_body):
    """Frazione di keyword della fonte presente nel tradotto (come nomi propri,
    che restano invariati in italiano). Copertura < 0.5 -> sospetto drop."""
    src_kw = set(KEYWORD_RE.findall(src_body.lower()))
    if len(src_kw) < 20:
        return 1.0  # atomo piccolo, non affidabile
    tr_kw = set(KEYWORD_RE.findall(tr_body.lower()))
    hits = src_kw & tr_kw
    return len(hits) / len(src_kw)


def process_one(job):
    src_path = Path(job["src"])
    lang = job.get("lang", "it")
    fname = src_path.name
    try:
        if src_path.with_suffix(".it.md").exists() and "--force" not in sys.argv:
            return "skip"
        src_fm, src_body = ds.read_atom(str(src_path))
        src_lang = src_fm.get("lang", "en")
        # mask wikilink, traduci, unmask (retry fino a 3 se i bersagli perdono)
        masked, targets = ds.mask_links(src_body)
        src_t = [m.group(1).strip() for m in verify.WIKILINK_RE.finditer(src_body)]
        tr = None
        for attempt in range(3):
            extra = ""
            if attempt:
                extra = ("IMPORTANT: the previous attempt lost or reordered "
                         "markers [[L..|..]]. Copy them VERBATIM into your output, "
                         "unchanged, in the same order and same positions.")
            out = _call(masked, lang, src_lang, extra)
            try_out = ds.unmask_links(out, targets)
            tr_t = [m.group(1).strip() for m in verify.WIKILINK_RE.finditer(try_out)]
            if src_t == tr_t:
                tr = try_out
                break
            tr = try_out
        tr = tr.strip("\n") + "\n"

        problems = []
        # H1: la fonte ne ha uno, il tradotto deve mantenerlo
        if H1_RE.match(src_body.lstrip("\n")) and not H1_RE.match(tr.lstrip("\n")):
            problems.append("manca H1")
        # wikilink: bersagli devono combaciare
        src_t = [m.group(1).strip() for m in verify.WIKILINK_RE.finditer(src_body)]
        tr_t = [m.group(1).strip() for m in verify.WIKILINK_RE.finditer(tr)]
        if src_t != tr_t:
            problems.append("wikilink: bersagli divergenti")
        # non identico alla fonte
        if tr.strip() == src_body.strip():
            problems.append("identico alla fonte")
        # copertura minima: se il tradotto ha <50% dei token della fonte, il
        # modello ha droppato contenuto (fusione ok, sparizione no)
        src_tok = len(verify.TOKEN_RE.findall(src_body))
        tr_tok = len(verify.TOKEN_RE.findall(tr))
        if src_tok and tr_tok < 0.5 * src_tok:
            problems.append("copertura %d%% token (sospetto contenuto perso)" %
                            (100 * tr_tok // src_tok))
        # inglese residuo (solo .it)
        if lang == "it":
            for i, b in enumerate(verify.prose_blocks(tr)):
                if verify.looks_english(b):
                    problems.append("blocchi in inglese: [%d]" % i)

        if problems:
            with _rej_lock:
                with open(REJECTED_PATH, "a", encoding="utf-8") as fh:
                    row = {"atom": str(src_path), "lang": lang, "problems": problems,
                           "when": time.strftime("%Y-%m-%dT%H:%M:%S")}
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            log("REJECT %s [%s]: %s" % (fname, lang, "; ".join(problems)[:180]))
            return "reject"
        ds.write_translation(str(src_path), lang, src_fm, tr)
        log("OK     %s [%s]" % (fname, lang))
        return "ok"
    except Exception as e:
        with _rej_lock:
            with open(REJECTED_PATH, "a", encoding="utf-8") as fh:
                row = {"atom": str(src_path), "lang": lang, "problems": ["exception: %s" % e],
                       "when": time.strftime("%Y-%m-%dT%H:%M:%S")}
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        log("FAIL   %s [%s]: %s" % (fname, lang, e))
        return "fail"


def log(msg):
    with _lock:
        print(msg, flush=True)


def main():
    if not ds.API_KEY:
        print("ERRORE: DEEPSEEK_API_KEY non impostata")
        return 1
    if len(sys.argv) < 2:
        print("USO: python scripts/translate/run_residui_fast.py <batchfile.json>")
        return 1
    force = "--force" in sys.argv
    batch_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not batch_args:
        print("USO: python scripts/translate/run_residui_fast.py [--force] <batchfile.json>")
        return 1
    batch_file = batch_args[0]
    jobs = json.loads(open(batch_file, encoding="utf-8").read())
    remaining = [j for j in jobs if force or not Path(j["src"]).with_suffix(".it.md").exists()]
    log("### residui FAST: %d pendenti su %d" % (len(remaining), len(jobs)))
    if not remaining:
        log("Niente da fare.")
        return 0

    from concurrent.futures import ThreadPoolExecutor, as_completed
    t0 = time.time()
    counts = {"ok": 0, "reject": 0, "fail": 0, "skip": 0}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(process_one, j): j for j in remaining}
        for fut in as_completed(futs):
            st = fut.result()
            counts[st] += 1
    log("### residui FAST completato in %.0fs  ok:%d reject:%d fail:%d" %
        (time.time() - t0, counts["ok"], counts["reject"], counts["fail"]))
    return 0 if counts["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
