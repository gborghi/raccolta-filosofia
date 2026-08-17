# -*- coding: utf-8 -*-
"""Tag each Philosophy atom semantically via DeepSeek V4 Flash, batch di 20.
Scrive data/tags/<Philosopher>.json con per-atom tags, non sovrascrive tag esistenti.
"""
import json, os, sys, time, urllib.request, hashlib, re
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
VAULT = os.path.normpath(os.path.join(ROOT, "..", "VaultPhilosophy"))
DATA_DIR = os.path.join(ROOT, "data")
TAGS_DIR = os.path.join(DATA_DIR, "tags")
TAXONOMY_PATH = os.path.join(DATA_DIR, "taxonomy.json")
CACHE_PATH = os.path.join(DATA_DIR, "atom_tag_cache.jsonl")

DEEPSEEK_HOST = os.environ.get("DEEPSEEK_HOST", "https://api.deepseek.com")
DEEPSEEK_MODEL = "deepseek-v4-flash"
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
WORKERS = 3

H1_RE = re.compile(r"^#\s+.*(?:\n|$)")

# carica tassonomia
with open(TAXONOMY_PATH) as f:
    tax = json.load(f)

# id -> {id, label_en, label_it, type, ...}
TAX_BY_ID = {}
for tax_key, node_type in [
    ("axes", "axis"), ("positions", "position"), ("concepts", "concept"),
    ("arguments", "argument"), ("figures", "figure"), ("forms", "form"), ("schools", "school"),
]:
    for node in tax.get(tax_key, []):
        TAX_BY_ID[node["id"]] = {**node, "type": node_type, "tax_key": tax_key}

TAX_OPTIONS = []
for tid, info in sorted(TAX_BY_ID.items()):
    TAX_OPTIONS.append(f'{tid} [{info["type"]}] — {info["label_en"]} / {info.get("label_it","")}')

TAX_TEXT = "\n".join(TAX_OPTIONS)

SYSTEM_PROMPT = f"""You are a philosophy taxonomy expert. Given a short text from a philosophical work, assign relevant tags from the controlled vocabulary below.

Available tags (id [type] — en_label / it_label):
{TAX_TEXT}

Rules:
- Assign ONLY tags that genuinely apply to the SPECIFIC text provided, not to the work as a whole
- Choose from the available ids above — NEVER invent new ones
- Return a JSON object with arrays of tag ids keyed by type: {{"axes":[],"positions":[],"concepts":[],"arguments":[],"figures":[],"forms":[],"schools":[]}}
- Return ONLY valid JSON, nothing else
- If nothing applies, return empty arrays
- Maximum 5 tags total"""


def load_cache():
    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    e = json.loads(line)
                    cache[e["h"]] = e["tags"]
    return cache


def save_cache(cache):
    with open(CACHE_PATH, "w") as f:
        for h, tags in cache.items():
            f.write(json.dumps({"h": h, "tags": tags}) + "\n")


def load_tags_file(phil):
    p = os.path.join(TAGS_DIR, f"{phil}.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {}


def save_tags_file(phil, data):
    p = os.path.join(TAGS_DIR, f"{phil}.json")
    with open(p, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def hash_text(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def strip_frontmatter(md):
    if md.startswith("---"):
        idx = md.find("---", 3)
        if idx != -1:
            md = md[idx + 3:]
    return md.strip()


def tag_one(text, label="", retries=3):
    h = hash_text(text)
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text[:6000]},
        ],
        "temperature": 0.1,
        "max_tokens": 512,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{DEEPSEEK_HOST}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
            content = result["choices"][0]["message"]["content"]
            tags = json.loads(content)
            # validate
            out = {}
            for k in ["axes", "positions", "concepts", "arguments", "figures", "forms", "schools"]:
                ids = tags.get(k, [])
                if isinstance(ids, list):
                    valid = [i for i in ids if i in TAX_BY_ID]
                    if valid:
                        out[k] = valid
            return h, out
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
    return h, {}


def collect_atoms():
    """Raccoglie tutti gli atomi dalla vault, raggruppati per filosofo e opera."""
    phil_dir = os.path.join(VAULT, "Philosophers")
    atoms = []
    for phil in sorted(os.listdir(phil_dir)):
        atomized = os.path.join(phil_dir, phil, "Atomized")
        if not os.path.isdir(atomized):
            continue
        for work in sorted(os.listdir(atomized)):
            work_dir = os.path.join(atomized, work)
            if not os.path.isdir(work_dir):
                continue
            for fname in sorted(os.listdir(work_dir)):
                if not fname.endswith(".md") or fname.endswith(".it.md") or fname.endswith(".en.md") or fname.endswith(".la.md"):
                    continue
                fpath = os.path.join(work_dir, fname)
                with open(fpath) as f:
                    text = strip_frontmatter(f.read())
                if len(text) < 50:
                    continue  # skip empty/tiny atoms
                atom_id = fname[:-3]
                atoms.append((phil, work, atom_id, fpath, text))
    return atoms


def main():
    if not API_KEY:
        print("Set DEEPSEEK_API_KEY"); sys.exit(1)

    cache = load_cache()
    print(f"Cache: {len(cache)} entries")

    all_atoms = collect_atoms()
    print(f"Atoms: {len(all_atoms)} total")

    # filter out already cached
    pending = []
    already = 0
    for phil, work, atom_id, fpath, text in all_atoms:
        h = hash_text(text)
        if h in cache:
            already += 1
        else:
            pending.append((phil, work, atom_id, fpath, text, h))
    print(f"Already tagged: {already}, Pending: {len(pending)}")

    if not pending:
        print("All atoms already tagged!")
        return

    # group by philosopher
    by_phil = {}
    for item in pending:
        by_phil.setdefault(item[0], []).append(item)

    total = len(pending)
    done = 0

    for phil, items in sorted(by_phil.items()):
        print(f"\n=== {phil}: {len(items)} atomi da taggare ===")
        tags_data = load_tags_file(phil)

        for i in range(0, len(items), WORKERS):
            batch = items[i:i + WORKERS]
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futures = {ex.submit(tag_one, text, atom_id): (atom_id, work, h)
                          for (_, work, atom_id, _, text, h) in batch}
                for fut in as_completed(futures):
                    atom_id, work, h = futures[fut]
                    try:
                        th, tags = fut.result()
                        if tags:
                            cache[h] = tags
                            # write to tags_data
                            w = tags_data.setdefault(work, {})
                            w.setdefault("atoms", {})[atom_id] = tags
                    except Exception as e:
                        print(f"  FAIL {phil}/{work}/{atom_id}: {e}")

            done += len(batch)
            # save incrementally
            save_tags_file(phil, tags_data)
            save_cache(cache)
            print(f"  {phil}: {min(i+WORKERS, len(items))}/{len(items)} | total {done}/{total}")


    print(f"\nDone! Tagged {len(cache) - already} new atoms (total cache: {len(cache)})")
    print("Now run: SPA=1 node preprocess.mjs && node ./quartz/bootstrap-cli.mjs build")


if __name__ == "__main__":
    main()
