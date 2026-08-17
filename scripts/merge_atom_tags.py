# -*- coding: utf-8 -*-
"""Merge atom_tag_cache.jsonl (h->tags) into data/tags/<Philosopher>.json as 'atoms' key."""
import json, os, sys, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
VAULT = os.path.normpath(os.path.join(ROOT, "..", "VaultPhilosophy"))
DATA_DIR = os.path.join(ROOT, "data")
TAGS_DIR = os.path.join(DATA_DIR, "tags")
CACHE_PATH = os.path.join(DATA_DIR, "atom_tag_cache.jsonl")

def hash_text(t):
    return hashlib.sha1(t.encode("utf-8")).hexdigest()

def strip_fm(md):
    if md.startswith("---"):
        i = md.find("---", 3)
        if i != -1:
            md = md[i+3:]
    return md.strip()

def load_cache():
    c = {}
    with open(CACHE_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                e = json.loads(line)
                c[e["h"]] = e["tags"]
    return c

def main():
    cache = load_cache()
    print(f"Cache: {len(cache)} entries")

    # Map hash -> (phil, work, atom_id) by re-reading atoms
    phil_dir = os.path.join(VAULT, "Philosophers")
    tag_updates = {}  # phil -> {work_key -> {atom_id: tags}}

    for phil in sorted(os.listdir(phil_dir)):
        atomized = os.path.join(phil_dir, phil, "Atomized")
        if not os.path.isdir(atomized):
            continue
        for work in sorted(os.listdir(atomized)):
            wd = os.path.join(atomized, work)
            if not os.path.isdir(wd):
                continue
            for fn in sorted(os.listdir(wd)):
                if not fn.endswith(".md") or fn.endswith(".it.md") or fn.endswith(".en.md") or fn.endswith(".la.md"):
                    continue
                fp = os.path.join(wd, fn)
                with open(fp) as f:
                    text = strip_fm(f.read())
                h = hash_text(text)
                tags = cache.get(h)
                if tags:
                    tag_updates.setdefault(phil, {}).setdefault(work, {})[fn[:-3]] = tags

    total_atoms = 0
    for phil, works in sorted(tag_updates.items()):
        path = os.path.join(TAGS_DIR, f"{phil}.json")
        data = {}
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
        n = 0
        for work_key, atoms in works.items():
            w = data.setdefault(work_key, {})
            w["atoms"] = atoms
            n += len(atoms)
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        total_atoms += n
        print(f"  {phil}: {n} atomi taggati in {len(works)} opere")

    print(f"\nTotale: {total_atoms} atomi con tag per-atomo scritti")

if __name__ == "__main__":
    main()
