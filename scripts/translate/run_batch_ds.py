#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Traduce un batch esplicito di atomi (path in un file JSON) con DeepSeek API.

    DEEPSEEK_API_KEY=sk-... python scripts/translate/run_batch_ds.py data/ds_batches/batch_000.json
    DEEPSEEK_API_KEY=sk-... DEEPSEEK_WORKERS=2 python scripts/translate/run_batch_ds.py <batchfile>

Stesso motore di run_author_ds.py, ma la worklist arriva da un file JSON:
    [{"src": "<abs path .md>", "lang": "it"}, ...]
Log rejected su scripts/translate/run_logs/ds_batch_rejected.jsonl.
"""
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_author_ds as ds  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
LOG_DIR = os.path.join(HERE, "run_logs")
REJECTED_PATH = os.path.join(LOG_DIR, "ds_batch_rejected.jsonl")

_lock = threading.Lock()
_rej_lock = threading.Lock()


def log(msg):
    with _lock:
        print(msg, flush=True)


def process_one(job, cache):
    src_path = job["src"]
    lang = job.get("lang", "it")
    fname = os.path.basename(src_path)
    try:
        if os.path.exists(ds.sibling_path(src_path, lang)):
            return "skip", None
        src_fm, src_body = ds.read_atom(src_path)
        tr_body, missing = ds.translate_atom(src_path, lang, cache)
        problems = ds.validate(src_body, tr_body, lang)
        if problems:
            ds.record_reject(src_path, lang, problems, REJECTED_PATH)
            log("REJECT %s [%s]: %s" % (fname, lang, "; ".join(problems)[:180]))
            return "reject", len(missing)
        ds.write_translation(src_path, lang, src_fm, tr_body)
        if missing:
            log("OK     %s [%s] -- %d link persi" % (fname, lang, len(missing)))
        return "ok", len(missing)
    except Exception as e:
        ds.record_reject(src_path, lang, ["exception: %s" % e], REJECTED_PATH)
        log("FAIL   %s [%s]: %s" % (fname, lang, e))
        return "fail", None


def main():
    if not ds.API_KEY:
        print("ERRORE: DEEPSEEK_API_KEY non impostata")
        return 1
    if len(sys.argv) < 2:
        print("USO: python scripts/translate/run_batch_ds.py <batchfile.json>")
        return 1

    batch_file = sys.argv[1]
    with open(batch_file, encoding="utf-8") as fh:
        pending = json.load(fh)

    remaining = [j for j in pending if not os.path.exists(ds.sibling_path(j["src"], j.get("lang", "it")))]
    log("### batch %s: %d pendenti su %d" % (os.path.basename(batch_file), len(remaining), len(pending)))
    if not remaining:
        log("Niente da fare.")
        return 0

    # Cache per-batch: evita race su scritture append concorrenti allo stesso
    # file (processi paralleli che interleave linee -> byte invalidi UTF-8).
    # La cache e' solo ottimizzazione: rigenerarla per batch costa zero.
    cache = ds.Cache(os.path.join(ROOT, "data", "ds_translate_cache_%s.jsonl" % Path(batch_file).stem))
    log("Cache: %d blocchi caldi" % len(cache.d))

    from concurrent.futures import ThreadPoolExecutor, as_completed

    workers = max(1, min(ds.WORKERS, len(remaining)))
    t0 = time.time()
    counts = {"ok": 0, "skip": 0, "reject": 0, "fail": 0, "lost": 0}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_one, j, cache): j for j in remaining}
        for fut in as_completed(futs):
            status, lost = fut.result()
            counts[status] = counts.get(status, 0) + 1
            if lost:
                counts["lost"] += lost

    elapsed = time.time() - t0
    log("### batch completato in %.0fs  ok:%d reject:%d fail:%d skip:%d"
        % (elapsed, counts["ok"], counts["reject"], counts["fail"], counts["skip"]))
    return 0 if counts["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
