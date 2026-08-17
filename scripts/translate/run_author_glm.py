#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Traduce atomi pendenti di un filosofo con GLM API (GLM-4).

    GLM_API_KEY=... python scripts/translate/run_author_glm.py Hegel
    GLM_API_KEY=... GLM_WORKERS=16 python scripts/translate/run_author_glm.py Hegel

Genera automaticamente la worklist dagli atomi senza traduzione.
Riprendibile: salva cache blocchi e rejected log.
Versione GLM del modulo run_author_ds.py (DeepSeek).
"""
import hashlib
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
import verify  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
VAULT_ROOT = os.path.normpath(os.path.join(ROOT, "..", "VaultPhilosophy"))
LOG_DIR = os.path.join(HERE, "run_logs")

GLM_HOST = os.environ.get("GLM_HOST", "https://open.bigmodel.cn/api/paas/v4")
GLM_MODEL = os.environ.get("GLM_MODEL", "glm-4-plus")
API_KEY = os.environ.get("GLM_API_KEY", "")
WORKERS = int(os.environ.get("GLM_WORKERS", "12"))

# ---------------------------------------------------------------------------
# wikilink masking (identico a run_author_ds.py)
# ---------------------------------------------------------------------------
WIKILINK_RE = re.compile(r"\[\[([^\]|\n]+)(?:\|([^\]\n]*))?\]\]")
CODE_RE = re.compile(r"\[\[(L\d{2,})\|([^\]]*)\]\]")
MALFORMED_CODE_RE = re.compile(
    r"(?:\[\[|【)(L\d{2,})\s*[|>:｜＞：\]］】]?\s*([^\[\]|｜【】［］]+?)\s*[\]］】]{1,2}")
UNCLOSED_CODE_RE = re.compile(
    r"(?:\[\[|【)(L\d{2,})\s*[|>:｜＞：\]］】]?\s*([^\[\]|｜【】［］“”«»\n]{1,60}?)\s*(?=[”»])")
POISONED_RE = re.compile(r"\[\[L\d{1,3}\b")
CJK_RE = re.compile("[぀-ヿ㐀-䶿一-鿿가-힯！-｠]")

LANG_NAMES = {
    "it": "Italiano", "en": "Inglese", "fr": "Francese", "de": "Tedesco",
    "es": "Spagnolo", "la": "Latino", "grc": "Greco antico", "pt": "Portoghese",
}

_lock = threading.Lock()
_rej_lock = threading.Lock()


def mask_links(block):
    targets = []
    def sub(m):
        target, label = m.group(1), m.group(2)
        targets.append(target)
        return "[[L%02d|%s]]" % (len(targets), label if label is not None else target)
    return WIKILINK_RE.sub(sub, block), targets


def unmask_links(tr_block, targets):
    def sub(m):
        idx = int(m.group(1)[1:]) - 1
        label = m.group(2).strip()
        if idx < 0 or idx >= len(targets):
            return m.group(0)
        return "[[%s|%s]]" % (targets[idx], label or targets[idx])
    return CODE_RE.sub(sub, tr_block)


def repair_mask_codes(text):
    text = MALFORMED_CODE_RE.sub(r"[[\1|\2]]", text)
    text = UNCLOSED_CODE_RE.sub(_unclosed_code, text)
    return _drop_stray_close(text)


def _unclosed_code(m):
    tail = m.string[m.end():m.end() + 8]
    if "]" in tail or "］" in tail or "】" in tail:
        return m.group(0)
    label = m.group(2)
    trimmed = label.rstrip(" ,;:!?.'`")
    if not trimmed:
        return m.group(0)
    return "[[%s|%s]]%s" % (m.group(1), trimmed, label[len(trimmed):])


def _drop_stray_close(text):
    buf, depth, i = [], 0, 0
    while i < len(text):
        if text.startswith("[[", i):
            depth += 1
            buf.append("[[")
            i += 2
        elif text.startswith("]]", i):
            if depth:
                depth -= 1
                buf.append("]]")
            i += 2
        else:
            buf.append(text[i])
            i += 1
    return "".join(buf)


def strip_mask_codes(text):
    ANY_CODE_RE = re.compile(r"\[\[L\d{2,}\|?([^\]|]*)\]\]")
    return ANY_CODE_RE.sub(lambda m: m.group(1), text)


def codes_of(text):
    return [g[0] for g in CODE_RE.findall(text)]


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------
def call_glm(messages, max_tokens, temperature=0):
    body = json.dumps({
        "model": GLM_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }).encode("utf-8")
    last_err = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                GLM_HOST + "/chat/completions",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + API_KEY,
                },
            )
            r = json.loads(urllib.request.urlopen(req, timeout=300).read())
            out = r["choices"][0]["message"]["content"].strip()
            if out:
                return out
            last_err = "empty completion"
        except Exception as e:
            last_err = repr(e)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("GLM call failed: %s" % last_err)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
def _sha(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


class Cache:
    def __init__(self, path):
        self.path = path
        self.d = {}
        self._lock = threading.Lock()
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if ln:
                        try:
                            r = json.loads(ln)
                        except ValueError:
                            continue
                        self.d[r["h"]] = r["tr"]
        self._fh = open(path, "a", encoding="utf-8")

    def _key(self, s, lang):
        return _sha(lang + "\x00" + s)

    def get(self, s, lang):
        with self._lock:
            return self.d.get(self._key(s, lang))

    def put(self, s, lang, tr):
        h = self._key(s, lang)
        with self._lock:
            if h in self.d:
                return
            self.d[h] = tr
            self._fh.write(json.dumps({"h": h, "lang": lang, "src": s, "tr": tr},
                                      ensure_ascii=False) + "\n")
            self._fh.flush()


# ---------------------------------------------------------------------------
# translation engine
# ---------------------------------------------------------------------------
PART_SPLIT_RE = re.compile(r"(\n[ \t]*\n)")
HEADING_RE = re.compile(r"\A([ \t]*#{1,6}[ \t]+)(.*)\Z", re.S)
BOILERPLATE_RE = re.compile(
    r"project gutenberg|gutenberg\.org|gutenberg-tm|www\.|https?://|archive foundation"
    r"|copyright royalt|electronic works?\b|redistribut|\brefund\b|\btrademark\b", re.I)


def _system_prompt(tgt_lang, src_lang, has_links):
    tgt_name = LANG_NAMES.get(tgt_lang, tgt_lang)
    src_name = LANG_NAMES.get(src_lang, src_lang)
    s = (
        "You are a literary translator of philosophical prose. "
        "Translate the following %s passage into %s. "
        "Preserve the author's register: do not modernise, do not soften, "
        "do not explain. Add no notes, no preface, no commentary. "
        "Keep every sentence whole and return exactly ONE paragraph with no blank lines. "
        "IMPORTANT: preserve the paragraph structure of the source. "
        "Never merge two source paragraphs into one, never split one into two. "
        "Output ONLY the %s translation, nothing else."
    ) % (src_name, tgt_name, tgt_name)
    if has_links:
        s += (
            " Every [[Lxx|word]] marker MUST reappear EXACTLY as [[Lxx|translated]]: "
            "keep the Lxx code, keep the vertical bar '|', "
            "translate ONLY the word after '|'. Never drop a marker, never flatten "
            "it to plain text, never reorder the markers."
        )
    return s


def _corrupt_block(src, tr):
    if POISONED_RE.search(tr):
        return True
    if CJK_RE.search(tr) and not CJK_RE.search(src):
        return True
    return False


def translate_block(src_block, tgt_lang, src_lang, cache, tries=3):
    masked, targets = mask_links(src_block)
    want = ["L%02d" % (i + 1) for i in range(len(targets))]

    if not want:
        cached = cache.get(src_block, tgt_lang)
        if cached:
            return cached, []

        msgs = [
            {"role": "system", "content": _system_prompt(tgt_lang, src_lang, False)},
            {"role": "user", "content": src_block},
        ]
        budget = max(16384, min(65536, len(src_block) * 16))
        for _ in range(tries):
            out = call_glm(msgs, budget)
            out = repair_mask_codes(out)
            out = _clean_output(out)
            if not _is_fabricated(src_block, out):
                cache.put(src_block, tgt_lang, out)
                return out, []
        # Se fabricato, ritorna il testo originale marcato come rifiutato
        return src_block, []

    best, best_got = None, []
    for attempt in range(tries):
        cached = cache.get(masked, tgt_lang)
        if cached:
            out = cached
        else:
            msgs = [
                {"role": "system", "content": _system_prompt(tgt_lang, src_lang, True)},
                {"role": "user", "content": masked},
            ]
            budget = max(16384, min(65536, len(src_block) * 16))
            out = call_glm(msgs, budget)
            out = repair_mask_codes(out)
            out = _clean_output(out)

        if _is_fabricated(src_block, out):
            continue
        got = codes_of(out)
        if got == want:
            cache.put(masked, tgt_lang, out)
            return unmask_links(out, targets), []
        if best is None or len(set(got) & set(want)) > len(set(best_got) & set(want)):
            best, best_got = out, got
        if not got:
            break

    if best is None:
        return src_block, []
    cache.put(masked, tgt_lang, best)
    tr = unmask_links(best, targets)
    missing = [targets[int(c[1:]) - 1] for c in want if c not in best_got]
    return tr, missing


def _clean_output(s):
    s = s.replace("...", "…")
    s = re.sub(r"\s*…\s*$", ".", s, flags=re.M)
    s = re.sub(r"\s*…\s+(?=[A-ZÀ-Þ\[\"«])", ". ", s)
    s = re.sub(r"\s*…\s*", ", ", s)
    s = re.sub(r"\s+([.,;:!?])", r"\1", s)
    s = re.sub(r",\s*\.", ".", s)
    return re.sub(r"\s*\n[ \t]*\n+\s*", " ", s).strip()


def _is_fabricated(src_block, tr_block):
    if len(src_block) < 120:
        return False
    return len(tr_block) > 2 * len(src_block) + 80


def is_truncated(src_block, tr_block):
    if len(src_block) < 200:
        return False
    return 2 * len(tr_block) + 80 < len(src_block)


def translate_atom(src_path, tgt_lang, cache):
    src_fm, body = read_atom(src_path)
    src_lang = src_fm.get("lang", "en")
    parts = PART_SPLIT_RE.split(body)
    out, missing = [], []
    for k, part in enumerate(parts):
        if k % 2:
            out.append(part)
            continue
        s = part.strip()
        if not s or not verify.WORD_RE.search(s) or BOILERPLATE_RE.search(s):
            out.append(part)
            continue
        tr = cache.get(s, tgt_lang)
        if tr is None:
            m = HEADING_RE.match(s)
            if m:
                hashes, text = m.group(1), m.group(2)
                tr_text, miss = translate_block(text, tgt_lang, src_lang, cache)
                tr = hashes + tr_text.lstrip()
            else:
                tr, miss = translate_block(s, tgt_lang, src_lang, cache)
            missing.extend(miss)
            cache.put(s, tgt_lang, tr)
        tr = strip_mask_codes(tr)
        lead = part[:len(part) - len(part.lstrip())]
        trail = part[len(part.rstrip()):]
        qm = re.match(r"(>+\s*)", s)
        if qm and not tr.startswith(">"):
            tr = qm.group(1) + tr
        out.append(lead + tr.strip() + trail)
    return "".join(out), missing


# ---------------------------------------------------------------------------
# lettura/scrittura atomi
# ---------------------------------------------------------------------------
def read_atom(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return verify.parse_fm(text)


def build_fm(src_fm, tgt_lang):
    out = ["---"]
    out.append('philosopher: "%s"' % src_fm.get("philosopher", ""))
    out.append('lang: "%s"' % tgt_lang)
    out.append('work: "%s"' % src_fm.get("work", ""))
    out.append("atom_n: %s" % src_fm.get("atom_n", ""))
    out.append("---")
    return "\n".join(out) + "\n"


def sibling_path(src_path, lang):
    return src_path[:-3] + "." + lang + ".md"


def write_translation(src_path, tgt_lang, src_fm, tr_body):
    path = sibling_path(src_path, tgt_lang)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(build_fm(src_fm, tgt_lang))
        fh.write(tr_body if tr_body.startswith("\n") else "\n" + tr_body)
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# validazione
# ---------------------------------------------------------------------------
def validate(src_body, tr_body, tgt_lang):
    problems = []
    sp = verify.prose_blocks(src_body)
    tp = verify.prose_blocks(tr_body)
    if len(sp) != len(tp):
        problems.append("blocchi %d fonte vs %d tradotti" % (len(sp), len(tp)))
    else:
        fab = [(len(a), len(b)) for a, b in zip(sp, tp) if _is_fabricated(a, b)]
        if fab:
            problems.append("FABBRICATO in %d blocchi (%d -> %d)" % (len(fab), fab[0][0], fab[0][1]))
        trunc = [(len(a), len(b)) for a, b in zip(sp, tp) if is_truncated(a, b)]
        if trunc:
            problems.append("TRONCATO in %d blocchi (%d -> %d)" % (len(trunc), trunc[0][0], trunc[0][1]))

    st = [m.group(1).strip() for m in verify.WIKILINK_RE.finditer(src_body)]
    tt = [m.group(1).strip() for m in verify.WIKILINK_RE.finditer(tr_body)]
    invented = sorted(set(tt) - set(st))
    if invented:
        problems.append("wikilink inventati: %s" % invented[:6])

    nolabel = [m.group(1) for m in verify.WIKILINK_RE.finditer(tr_body) if m.group(2) is None]
    if nolabel:
        problems.append("wikilink senza etichetta: %s" % nolabel[:6])

    stray = POISONED_RE.findall(tr_body)
    if stray:
        problems.append("mask token residui: %d (%s)" % (len(stray), stray[0]))

    if verify.H1_RE.match(src_body.lstrip("\n")) and not verify.H1_RE.match(tr_body.lstrip("\n")):
        problems.append("manca H1")

    if tr_body.strip() == src_body.strip():
        problems.append("identico alla fonte")

    if tgt_lang == "it":
        left = [i for i, b in enumerate(tp) if verify.looks_english(b)]
        if left:
            problems.append("blocchi in inglese: %s" % left[:6])

    return problems


# ---------------------------------------------------------------------------
# worklist generation
# ---------------------------------------------------------------------------
def build_worklist(author_name):
    """Trova tutti gli atomi .md che non hanno il sibling .it.md."""
    atoms_dir = Path(VAULT_ROOT) / "Philosophers" / author_name / "Atomized"
    if not atoms_dir.is_dir():
        print("Directory non trovata: %s" % atoms_dir)
        return []

    pending = []
    for md_file in sorted(atoms_dir.rglob("*.md")):
        name = md_file.name
        # Salta i sibling di lingua (\.xx\.md)
        if re.search(r"\.[a-z]{2,3}\.md$", name):
            continue
        it_path = md_file.with_suffix(".it.md")
        if not it_path.exists():
            pending.append({
                "src": str(md_file),
                "lang": "it",
            })
    return pending


# ---------------------------------------------------------------------------
# main loop
# ---------------------------------------------------------------------------
def log(msg):
    with _lock:
        print(msg, flush=True)


def process_one(job, cache, rejected_path):
    src_path = job["src"]
    lang = job["lang"]
    fname = os.path.basename(src_path)
    try:
        if os.path.exists(sibling_path(src_path, lang)):
            return "skip", None
        src_fm, src_body = read_atom(src_path)
        tr_body, missing = translate_atom(src_path, lang, cache)
        problems = validate(src_body, tr_body, lang)
        if problems:
            record_reject(src_path, lang, problems, rejected_path)
            log("REJECT %s [%s]: %s" % (fname, lang, "; ".join(problems)[:180]))
            return "reject", len(missing)
        write_translation(src_path, lang, src_fm, tr_body)
        if missing:
            log("OK     %s [%s] -- %d link persi" % (fname, lang, len(missing)))
        return "ok", len(missing)
    except Exception as e:
        record_reject(src_path, lang, ["exception: %s" % e], rejected_path)
        log("FAIL   %s [%s]: %s" % (fname, lang, e))
        return "fail", None


def record_reject(path, lang, problems, rejected_path):
    os.makedirs(LOG_DIR, exist_ok=True)
    row = {
        "atom": os.path.relpath(path, VAULT_ROOT),
        "lang": lang,
        "problems": problems,
        "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with _rej_lock:
        with open(rejected_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    if not API_KEY:
        print("ERRORE: GLM_API_KEY non impostata")
        return 1

    if len(sys.argv) < 2:
        print("USO: python scripts/translate/run_author_glm.py <NomeFilosofo>")
        print("Es:   python scripts/translate/run_author_glm.py Hegel")
        return 1

    author = sys.argv[1]
    cache_path = os.path.join(ROOT, "data", "glm_translate_cache_%s.jsonl" % author.lower())
    rejected_path = os.path.join(LOG_DIR, "glm_rejected_%s.jsonl" % author.lower())

    # Build worklist
    pending = build_worklist(author)
    remaining = [j for j in pending if not os.path.exists(sibling_path(j["src"], j["lang"]))]
    log("### %s: %d traduzioni pendenti su %d totali (%.1f%% gia' fatti)"
        % (author, len(remaining), len(pending),
           100.0 * (len(pending) - len(remaining)) / max(1, len(pending))))

    if not remaining:
        log("Niente da fare.")
        return 0

    cache = Cache(cache_path)
    log("Cache: %d blocchi caldi" % len(cache.d))

    from concurrent.futures import ThreadPoolExecutor, as_completed

    t0 = time.time()
    counts = {"ok": 0, "skip": 0, "reject": 0, "fail": 0, "lost": 0}
    done = 0
    total = len(remaining)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(process_one, j, cache, rejected_path): j for j in remaining}
        for fut in as_completed(futs):
            status, lost = fut.result()
            counts[status] = counts.get(status, 0) + 1
            if lost:
                counts["lost"] += lost
            done += 1
            if done % 50 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate if rate > 0 else 0
                log("... %d/%d (%.1f%%), %.1f u/h, ETA %.0fs  [ok:%d rej:%d fail:%d]"
                    % (done, total, 100.0 * done / total,
                       rate * 3600, eta,
                       counts["ok"], counts["reject"], counts["fail"]))

    elapsed = time.time() - t0
    log("\n### %s completato in %.0fs (%.1f min)" % (author, elapsed, elapsed / 60))
    log("    ok: %d  reject: %d  fail: %d  skip: %d  link persi: %d"
        % (counts["ok"], counts["reject"], counts["fail"], counts["skip"], counts["lost"]))
    log("    ritmo: %.1f unita'/ora" % (counts["ok"] / elapsed * 3600 if elapsed > 0 else 0))

    if counts["reject"] or counts["fail"]:
        log("    rejected log: %s" % rejected_path)
    return 0 if counts["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
