#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Traduce atomi residui blocco-per-blocco, una chiamata per blocco.

I batch normali falliscono su atomi con molti paragrafi: DeepSeek fonde due
paragrafi in uno e verify.py rifiuta ("blocchi N fonte vs M tradotti").

Il primo fallback con marker numerici [[B01]]..[[Bnn]] in UN'UNICA chiamata
fallisce lo stesso: il modello restituisce tutti i marker ma alcuni segmenti
VUOTI (paragrafi corti -> risposta vuota), e prose_blocks li filtra via
WORD_RE. Quindi qui: UNA chiamata per blocco (CHUNK=1, un solo marker nel
prompt, impossibile fondere), retry sul blocco se vuoto o troppo corto, e
protezione dell'H1 (se il modello perde il '#', lo reinserisce).

Ordine critico: prima mask_links() (trasforma i [[wikilink]] reali in
[[L01|...]]), POI i marker [[Bnn]] — altrimenti la regex dei wikilink mangia
anche i marker e il modello non sa cosa riprodurre.

    DEEPSEEK_API_KEY=sk-... python scripts/translate/run_residui_blocks.py data/ds_batches/fallback_00.json
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

ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
LOG_DIR = os.path.join(HERE, "run_logs")
REJECTED_PATH = os.path.join(LOG_DIR, "ds_batch_rejected.jsonl")
WORKERS = int(os.environ.get("DEEPSEEK_WORKERS", "4"))
MAX_RETRY = int(os.environ.get("RESIDUI_RETRY", "3"))

_lock = threading.Lock()
_rej_lock = threading.Lock()

H1_RE = re.compile(r"^([ \t]*\r?\n)*[ \t]*#[ \t]+(.+?)[ \t]*$", re.M)


def _split_blocks(text):
    """Split del testo in blocchi (stesso criterio di verify.prose_blocks)."""
    return re.split(r"\n[ \t]*\n", text)


def _call(block, tgt_lang, src_lang, extra=""):
    """Una chiamata API: traduce UN blocco. Ritorna il testo pulito."""
    tgt_name = ds.LANG_NAMES.get(tgt_lang, tgt_lang)
    src_name = ds.LANG_NAMES.get(src_lang, src_lang)
    sys_prompt = (
        "You are a literary translator of philosophical prose. "
        "Translate the following %s passage into %s. "
        "Preserve the author's register; add no notes, no commentary. "
        "Keep paragraph structure. %s "
        "Output ONLY the translation, nothing else."
    ) % (src_name, tgt_name, extra)
    body = json.dumps({
        "model": ds.DEEPSEEK_MODEL,
        "temperature": 0,
        "max_tokens": 65536,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": block},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        ds.DEEPSEEK_HOST + "/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + ds.API_KEY},
    )
    r = json.loads(urllib.request.urlopen(req, timeout=600).read())
    out = r["choices"][0]["message"]["content"].strip()
    # fondono gli a-capo interni: il blocco tradotto deve restare UN blocco
    # (\r?\n perche' il modello restituisce CRLF su Windows)
    out = re.sub(r"\s*\r?\n[ \t]*\r?\n+\s*", " ", out)
    out = out.strip()
    return out


def _translate_block(src_block, tgt_lang, src_lang, is_h1):
    """Traduce un blocco con retry finche' non passa la verifica minima."""
    src_passes = bool(verify.WORD_RE.search(src_block))
    best = None
    for attempt in range(MAX_RETRY):
        extra = ""
        if is_h1:
            extra = "The text starts with a Markdown H1 heading '#'. Keep the leading '# ' exactly."
        elif not src_passes:
            # blocco di soli segni/numeri nella fonte: traduci comunque, ma e'
            # il contenuto (es. titoli brevi) a decidere; nessun requisito minimo
            pass
        if best is not None and not verify.WORD_RE.search(best):
            extra = (extra + " Your translation must contain at least one word "
                     "of at least 3 letters (e.g. 'Yes.' -> 'Certo.').").strip()
        out = _call(src_block, tgt_lang, src_lang, extra)
        if not out:
            continue
        if is_h1 and not out.startswith("#"):
            out = "# " + out.lstrip("#").strip()
        if not src_passes:
            # Blocco corto nella fonte ("No.", "I do."): NON passa WORD_RE e la
            # fonte non lo conta. La traduzione deve restare corta, altrimenti
            # il conteggio dei blocchi sbilancia (verify conta solo blocchi con
            # parola 3+). Accetta SOLO output che non passa il filtro.
            if not verify.WORD_RE.search(out):
                return out
            if best is None or len(out) < len(best):
                best = out
            extra = (extra + " This is a short interjection or reply. "
                     "Translate it in ONE or TWO words, e.g. 'No.' -> 'No.', "
                     "'I do.' -> 'Sì.'. Do NOT make it a full sentence.").strip()
            continue
        if best is None or len(out) > len(best):
            best = out
        if verify.WORD_RE.search(out):
            if tgt_lang == "it" and verify.looks_english(out):
                # tradotto ma rimasto inglese -> ritenta con istruzione
                extra = (extra + " The text you produced is still English. "
                         "Translate it FULLY into %s, no English words.") % tgt_lang
                continue
            return out
    return best


def translate_atom_one_by_one(masked_links, tgt_lang, src_lang):
    """Traduce un intero atomo (gia' mask_links) una chiamata per blocco."""
    blocks = _split_blocks(masked_links)
    out_blocks = []
    for i, b in enumerate(blocks):
        is_h1 = bool(H1_RE.match(b.lstrip("\n")))
        tr = _translate_block(b, tgt_lang, src_lang, is_h1)
        if tr is None:
            raise RuntimeError("blocco %d irriducibile: %r" % (i + 1, b[:80]))
        out_blocks.append(tr)
    return out_blocks


def rebuild_body(out_blocks, targets):
    """Ricombina i blocchi tradotti in un corpo, poi unmask dei wikilink."""
    body = "\n\n".join(b.strip("\n") for b in out_blocks)
    body = re.sub(r"\n[ \t]*\n+", "\n\n", body)
    body = ds.unmask_links(body, targets)
    return body.strip("\n") + "\n"


def process_one(job):
    src_path = Path(job["src"])
    lang = job.get("lang", "it")
    fname = src_path.name
    try:
        if src_path.with_suffix(".it.md").exists():
            return "skip"
        src_fm, src_body = ds.read_atom(str(src_path))
        src_lang = src_fm.get("lang", "en")
        # 1) wikilink -> [[Lnn|...]] 2) una chiamata per blocco
        masked_links, targets = ds.mask_links(src_body)
        out_blocks = translate_atom_one_by_one(masked_links, lang, src_lang)
        tr_body = rebuild_body(out_blocks, targets)
        problems = ds.validate(src_body, tr_body, lang)
        if problems:
            # dump del body tradotto per diagnosi del mismatch blocchi
            debug_path = os.path.join(LOG_DIR, "debug_" + fname[:-3] + ".md")
            try:
                with open(debug_path, "w", encoding="utf-8") as fh:
                    fh.write(tr_body)
            except OSError:
                pass
            with _rej_lock:
                with open(REJECTED_PATH, "a", encoding="utf-8") as fh:
                    row = {"atom": str(src_path), "lang": lang, "problems": problems,
                           "when": time.strftime("%Y-%m-%dT%H:%M:%S")}
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            log("REJECT %s [%s]: %s" % (fname, lang, "; ".join(problems)[:180]))
            return "reject"
        ds.write_translation(str(src_path), lang, src_fm, tr_body)
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
        print("USO: python scripts/translate/run_residui_blocks.py <batchfile.json>")
        return 1
    batch_file = sys.argv[1]
    jobs = json.loads(open(batch_file, encoding="utf-8").read())
    remaining = [j for j in jobs if not Path(j["src"]).with_suffix(".it.md").exists()]
    log("### residui una-chiamata-per-blocco: %d pendenti su %d" % (len(remaining), len(jobs)))
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
    log("### residui completato in %.0fs  ok:%d reject:%d fail:%d" %
        (time.time() - t0, counts["ok"], counts["reject"], counts["fail"]))
    return 0 if counts["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
