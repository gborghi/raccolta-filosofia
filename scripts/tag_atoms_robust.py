# -*- coding: utf-8 -*-
"""Robust per-atom semantic tagger. Resumable, handles API hangs, saves every 20 atoms."""
import json, os, sys, time, urllib.request, hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, TimeoutError as FTimeout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
DATA_DIR = os.path.join(ROOT, "data")
TAGS_DIR = os.path.join(DATA_DIR, "tags")
TAXONOMY_PATH = os.path.join(DATA_DIR, "taxonomy.json")
CACHE_PATH = os.path.join(DATA_DIR, "atom_tag_cache.jsonl")

DEEPSEEK_HOST = os.environ.get("DEEPSEEK_HOST", "https://api.deepseek.com")
DEEPSEEK_MODEL = "deepseek-v4-flash"
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
WORKERS = 6

with open(TAXONOMY_PATH) as f:
    tax = json.load(f)
TAX_BY_ID = {}
for tax_key, node_type in [("axes","axis"),("positions","position"),("concepts","concept"),
    ("arguments","argument"),("figures","figure"),("forms","form"),("schools","school")]:
    for node in tax.get(tax_key, []):
        TAX_BY_ID[node["id"]] = {**node, "type": node_type}

TAX_OPTIONS = [f'{tid} [{info["type"]}] {info["label_en"]}/{info.get("label_it","")}'
               for tid, info in sorted(TAX_BY_ID.items())]
SYSTEM_PROMPT = ("You tag a philosophy text. Return JSON {\"axes\":[],\"positions\":[],\"concepts\":[],"
    "\"arguments\":[],\"figures\":[],\"forms\":[],\"schools\":[]} with tag ids from:\n"
    + "\n".join(TAX_OPTIONS)
    + "\nOnly tags that apply to THIS text. Max 5. Valid JSON only.")

def load_cache():
    c = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    e = json.loads(line); c[e["h"]] = e["tags"]
    return c

def save_cache(c):
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w") as f:
        for h, tags in c.items():
            f.write(json.dumps({"h": h, "tags": tags}) + "\n")
    os.replace(tmp, CACHE_PATH)

def hash_text(t):
    return hashlib.sha1(t.encode("utf-8")).hexdigest()

def strip_fm(md):
    if md.startswith("---"):
        i = md.find("---", 3)
        if i != -1: md = md[i+3:]
    return md.strip()

def tag_one(text, aid):
    h = hash_text(text)
    body = {"model": DEEPSEEK_MODEL, "messages": [
        {"role":"system","content":SYSTEM_PROMPT},
        {"role":"user","content": text[:4000]}],
        "temperature": 0.0, "max_tokens": 400, "response_format": {"type":"json_object"}}
    req = urllib.request.Request(f"{DEEPSEEK_HOST}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type":"application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                r = json.loads(resp.read())
            tags = json.loads(r["choices"][0]["message"]["content"])
            out = {}
            for k in ["axes","positions","concepts","arguments","figures","forms","schools"]:
                ids = tags.get(k, [])
                if isinstance(ids, list):
                    v = [i for i in ids if i in TAX_BY_ID]
                    if v: out[k] = v
            return h, out
        except Exception:
            time.sleep(2)
    return h, {}

def collect_pending():
    phil_dir = os.path.normpath(os.path.join(ROOT, "..", "VaultPhilosophy", "Philosophers"))
    cache = load_cache()
    pending = []
    for phil in sorted(os.listdir(phil_dir)):
        atomized = os.path.join(phil_dir, phil, "Atomized")
        if not os.path.isdir(atomized): continue
        for work in sorted(os.listdir(atomized)):
            wd = os.path.join(atomized, work)
            if not os.path.isdir(wd): continue
            for fn in sorted(os.listdir(wd)):
                if not fn.endswith(".md") or fn.endswith(".it.md") or fn.endswith(".en.md") or fn.endswith(".la.md"):
                    continue
                fp = os.path.join(wd, fn)
                with open(fp) as f:
                    text = strip_fm(f.read())
                if len(text) < 50: continue
                h = hash_text(text)
                if h in cache: continue
                pending.append((phil, work, fn[:-3], text[:4000], h))
    return cache, pending

def main():
    if not API_KEY:
        print("Set DEEPSEEK_API_KEY"); sys.exit(1)
    cache, pending = collect_pending()
    print(f"Cache: {len(cache)}, Pending: {len(pending)}", flush=True)
    start = time.time(); done = 0
    for i in range(0, len(pending), WORKERS):
        batch = pending[i:i+WORKERS]
        try:
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futs = {ex.submit(tag_one, t, a): (a, h) for (_, _, a, t, h) in batch}
                done_futs, not_done = wait(futs, timeout=60)
                for fut in done_futs:
                    a, h = futs[fut]
                    try:
                        th, tags = fut.result(timeout=5)
                        cache[h] = tags  # cache even empty {} to avoid re-processing
                        done += 1
                    except Exception:
                        done += 1
                # skip hung futures
                for fut in not_done:
                    fut.cancel()
                    done += 1
        except Exception as e:
            print(f"batch error: {e}", flush=True)
        if done % 100 == 0:
            save_cache(cache)
            el = time.time()-start; rate = done/el*3600
            eta = (len(pending)-done)/rate if rate else 0
            print(f"{done}/{len(pending)} ({done*100/len(pending):.1f}%) cache={len(cache)} rate={rate:.0f}/h ETA={eta:.1f}h", flush=True)
    save_cache(cache)
    print(f"DONE! cache={len(cache)}", flush=True)

if __name__ == "__main__":
    main()
