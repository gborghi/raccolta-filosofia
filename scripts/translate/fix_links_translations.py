#!/usr/bin/env python3
"""Ripara i wikilink nelle traduzioni del vault: toglie quelli inventati e
recupera quelli persi rispetto alla fonte.

Uso:
    # Scan + stats (dry-run, nessuna chiamata API, nessuna scrittura)
    python scripts/translate/fix_links_translations.py --dry-run

    # Passata completa (fase 1 euristica + fase 2 LLM, modello via LLM_MODEL)
    python scripts/translate/fix_links_translations.py [--only SOTTOSTRINGA]...

    # Solo i file rimasti in drift (richiede --force per riprocessarli)
    python scripts/translate/fix_links_translations.py --only-drift --force

Logica (per ogni traduzione <fonte>.md -> <fonte>.<lang>.md con fonte presente):
  1) Fase 1 (euristica, senza API): toglie le quadre a [[TARGET|...]] se TARGET
     non e' un id valido del vocabolario oppure non e' linkato nella fonte;
     toglie anche le occorrenze in eccesso dei target validi rispetto al
     conteggio della fonte (conserva le prime N in ordine di testo).
  2) Fase 2 (LLM, modello da LLM_MODEL, temperature 0): se qualche target ha meno
     occorrenze della fonte, chiede di inserire SOLO quei wikilink nel punto
     esatto, avvolgendo il testo gia' presente (piccole flessioni ammesse),
     fino a raggiungere esattamente il conteggio della fonte (notazione xN).
  Verifica deterministica: testo spogliato dai link identico + conteggi per
  target esattamente uguali a quelli della fonte (max 3 tentativi, poi drift
  non bloccante).
  Recupero drift: se la verifica fallisce, prima una riparazione deterministica
  (i target non attesi diventano gli id attesi nell'ordine della fonte, poi le
  occorrenze in eccesso vengono private delle quadre), poi fino a 2 tentativi
  di correzione etichetta via LLM su bozze riparabili.
  Resume automatico in data/ds_links_resume.jsonl (chiave = percorso file
  relativo a vault.parent; sha = sha256 del body normalizzato da fase 1).
"""

import argparse
import datetime
import hashlib
import json
from collections import Counter
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ICT_QWEN = Path("/Users/g.borghi/Library/CloudStorage/Dropbox/insegnamento/ICT/qwen/api_key")

DASHSCOPE_URL = os.environ.get(
    "LLM_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions")
MODEL = os.environ.get("LLM_MODEL", "qwen3.7-flash")
# I modelli DeepSeek ragionano e consumano tutto il budget max_tokens in
# reasoning_content (content vuoto, finish_reason=length). Con thinking
# disabilitato rispondono direttamente in pochi secondi.
SUPPRESS_REASONING = "deepseek" in MODEL.lower() or "deepseek" in DASHSCOPE_URL.lower()

LINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")
FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.S)
WS_RE = re.compile(r"\s+")

_key = None
_resume_log_path = None


def _read_api_key() -> str:
    for src in (
        os.environ.get("LLM_API_KEY"),
        os.environ.get("QWEN_API_KEY"),
        os.environ.get("DASHSCOPE_API_KEY"),
        str(Path.home() / ".config" / "qwen" / "api_key"),
        str(ICT_QWEN),
    ):
        if not src:
            continue
        if Path(src).is_file():
            val = Path(src).read_text(encoding="utf-8").strip()
        else:
            val = src.strip()  # env vars possono contenere la chiave direttamente
        if val:
            return val
    raise SystemExit(
        "Nessuna API key trovata.\n"
        "  $QWEN_API_KEY / $DASHSCOPE_API_KEY\n"
        "  ~/.config/qwen/api_key\n"
        "  ICT/qwen/api_key\n"
        "Crea una chiave su https://dashscope.console.aliyun.com/"
    )


def _http_json(payload: dict, timeout: int) -> dict:
    global _key
    if _key is None:
        _key = _read_api_key()
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


def load_taxonomy_ids(path: Path) -> set[str]:
    tax = json.loads(path.read_text(encoding="utf-8"))
    ids: set[str] = set()
    for key in ("axes", "positions", "concepts", "figures", "schools", "forms", "arguments"):
        for item in tax.get(key, []):
            if isinstance(item, dict) and "id" in item:
                ids.add(item["id"])
    return ids


def extract_links(text: str) -> dict[str, str]:
    """Mappa target -> primo testo completo del wikilink trovato."""
    links: dict[str, str] = {}
    for m in LINK_RE.finditer(text):
        links.setdefault(m.group(1), m.group(0))
    return links


def link_counts(text: str) -> Counter:
    """Conteggio delle occorrenze per target (per la verifica esatta)."""
    return Counter(m.group(1) for m in LINK_RE.finditer(text))


def strip_links(text: str) -> str:
    """Testo con i wikilink ridotti al solo testo visibile (per confronto)."""
    t = LINK_RE.sub(lambda m: m.group(2) or m.group(1), text)
    return WS_RE.sub(" ", t).strip()


def phase1_fix(body: str, src_targets: set[str], valid_ids: set[str],
               src_counts: Counter | None = None) -> tuple[str, int]:
    """Toglie le quadre ai wikilink con target non valido o non linkato nella fonte.

    Con src_counts, toglie anche le occorrenze in eccesso dei target validi
    oltre il conteggio della fonte (conserva le prime N in ordine di testo).
    """
    removed = 0
    seen: Counter = Counter()

    def repl(m: re.Match) -> str:
        nonlocal removed
        target = m.group(1)
        label = m.group(2) if m.group(2) is not None else target
        if target not in valid_ids or target not in src_targets:
            removed += 1
            return label
        seen[target] += 1
        if src_counts is not None and seen[target] > src_counts[target]:
            removed += 1
            return label
        return m.group(0)

    return LINK_RE.sub(repl, body), removed


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _count_unlabeled(body: str, valid_ids: set[str]) -> int:
    n = 0
    for m in LINK_RE.finditer(body):
        if m.group(2) is None and m.group(1) in valid_ids:
            n += 1
    return n


def _verify(resp: str, body1: str, expected: set[str], src_counts: Counter) -> bool:
    """Testo spogliato identico, nessun target estraneo e conteggi esatti."""
    return (strip_links(resp) == strip_links(body1)
            and set(extract_links(resp).keys()) == expected
            and all(link_counts(resp).get(t, 0) == src_counts[t] for t in expected))


def _restore_prompt(body: str, need: dict[str, int], src_links: dict[str, str],
                    lang: str) -> str:
    if lang == "it":
        gloss = lambda label: f'(nell\'originale: "{label}")'  # noqa: E731
        head = (
            "Nel testo qui sotto mancano alcuni wikilink rispetto all'originale.\n"
            "Inserisci SOLO questi wikilink:\n"
        )
        rules = (
            "Regole:\n"
            "- Il target di ogni wikilink (prima della barra '|') deve essere ESATTAMENTE uno "
            "degli ID elencati sopra, mai una parola del testo o un'etichetta.\n"
            "- La notazione (xN) dopo un ID indica quante occorrenze DISTINTE di quel "
            "wikilink devi inserire: ognuna in un punto diverso del testo.\n"
            "- Inserisci ESATTAMENTE N occorrenze di ogni wikilink elencato (x1 = una "
            "volta sola): mai di piu', mai di meno.\n"
            "- Inserisci ogni wikilink nel punto esatto in cui il concetto compare, "
            "avvolgendo il testo gia' presente (ammesse piccole flessioni: minuscole, plurali).\n"
            "- Non cambiare nessun'altra parola del testo.\n"
            "- Non aggiungere altri wikilink oltre a quelli elencati.\n"
            "- Non modificare i wikilink gia' presenti (ne' target ne' etichetta).\n"
            "- Rispondi SOLO con il testo completo corretto, senza commenti.\n"
        )
        body_label = "TESTO:"
    else:
        gloss = lambda label: f'(in the original: "{label}")'  # noqa: E731
        head = (
            "In the text below, some wikilinks are missing compared to the original.\n"
            "Insert ONLY these wikilinks:\n"
        )
        rules = (
            "Rules:\n"
            "- The target of every wikilink (before the bar '|') must be EXACTLY one of the "
            "IDs listed above, never a word of the text or a label.\n"
            "- The notation (xN) after an ID means how many DISTINCT occurrences of that "
            "wikilink you must insert, each at a different point of the text.\n"
            "- Insert EXACTLY N occurrences of every listed wikilink (x1 = just once): "
            "never more, never fewer.\n"
            "- Insert each wikilink at the exact spot where the concept appears, "
            "wrapping the already present text (minor inflection allowed: lowercase, plurals).\n"
            "- Do not change any other word.\n"
            "- Do not add any other wikilink beyond those listed.\n"
            "- Do not modify existing wikilinks (neither targets nor labels).\n"
            "- Reply with ONLY the complete corrected text, no commentary.\n"
        )
        body_label = "TEXT:"

    lines = [head]
    for t, n in sorted(need.items()):
        full = src_links.get(t, f"[[{t}]]")
        mm = LINK_RE.match(full)
        label = mm.group(2) if mm and mm.group(2) else t
        lines.append(f"- [[{t}]] (x{n}) {gloss(label)}")
    lines += ["", rules, "", body_label, "", body]
    return "\n".join(lines)


def _restore_once(body: str, need: dict[str, int], src_links: dict[str, str], lang: str,
                  max_tokens: int) -> str:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": _restore_prompt(body, need, src_links, lang)}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if SUPPRESS_REASONING:
        payload["thinking"] = {"type": "disabled"}
    resp = _http_json(payload, timeout=600)
    content = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return content.strip() if content else ""


def link_positions(text: str) -> dict[str, int]:
    """Mappa target -> posizione della prima occorrenza del link nella fonte."""
    pos: dict[str, int] = {}
    for m in LINK_RE.finditer(text):
        pos.setdefault(m.group(1), m.start())
    return pos


def _repair_links(resp: str, body1: str, expected: set[str], valid_ids: set[str],
                  src_pos: dict[str, int], src_counts: Counter) -> str | None:
    """Ripara deterministicamente target errati ed occorrenze in eccesso.

    Vale solo se il testo spogliato coincide: i target non attesi diventano gli
    id attesi nell'ordine della fonte (l'ordine dei concetti nella traduzione
    rispetta la fonte), poi le occorrenze oltre il conteggio della fonte
    vengono private delle quadre.
    """
    if strip_links(resp) != strip_links(body1):
        return None
    present = set(extract_links(resp).keys()) & valid_ids
    candidates = sorted(expected - present, key=lambda t: src_pos.get(t, 0))
    problems = [m for m in LINK_RE.finditer(resp) if m.group(1) not in expected]
    if problems and len(problems) != len(candidates):
        return None
    cand = iter(candidates)

    def repl(m: re.Match) -> str:
        if m.group(1) not in expected:
            target = next(cand)
            label = m.group(2) if m.group(2) is not None else m.group(1)
            return f"[[{target}|{label}]]"
        return m.group(0)

    fixed = LINK_RE.sub(repl, resp)
    seen: Counter = Counter()

    def trim(m: re.Match) -> str:
        target = m.group(1)
        label = m.group(2) if m.group(2) is not None else target
        seen[target] += 1
        if seen[target] > src_counts[target]:
            return label
        return m.group(0)

    trimmed = LINK_RE.sub(trim, fixed)
    if _verify(trimmed, body1, expected, src_counts):
        return trimmed
    return None


def _needs_relabel(resp: str, valid_ids: set[str]) -> bool:
    """Bozza riparabile via prompt: target non-id oppure link senza etichetta."""
    for m in LINK_RE.finditer(resp):
        if m.group(1) not in valid_ids or m.group(2) is None:
            return True
    return False


def _relabel_prompt(draft: str, missing: list[str], src_links: dict[str, str],
                    lang: str) -> str:
    if lang == "it":
        head = (
            "Il testo qui sotto contiene wikilink errati: il target di alcuni link "
            "non e' un id valido oppure manca l'etichetta ([[id]]).\n"
            "Correggi SOLO i wikilink:\n"
        )
        rules = (
            "Regole:\n"
            "- Il target di ogni wikilink (prima della barra '|') deve essere ESATTAMENTE "
            "uno degli ID elencati qui sotto.\n"
            "- Un link senza etichetta come [[id]] deve avvolgere la parola gia' presente "
            "nel testo: [[id|parola presente]] (piccole flessioni ammesse).\n"
            "- Non cambiare nessun'altra parola del testo.\n"
            "- Non aggiungere ne' rimuovere wikilink.\n"
            "- Rispondi SOLO con il testo completo corretto, senza commenti.\n"
        )
        body_label = "TESTO:"
    else:
        head = (
            "The text below contains wrong wikilinks: some targets are not valid ids, "
            "or the label is missing ([[id]]).\n"
            "Fix ONLY the wikilinks:\n"
        )
        rules = (
            "Rules:\n"
            "- The target of every wikilink (before the bar '|') must be EXACTLY one of the "
            "IDs listed below.\n"
            "- An unlabeled link like [[id]] must wrap the word already present in the "
            "text: [[id|present word]] (minor inflection allowed).\n"
            "- Do not change any other word.\n"
            "- Do not add or remove wikilinks.\n"
            "- Reply with ONLY the complete corrected text, no commentary.\n"
        )
        body_label = "TEXT:"

    lines = [head]
    for t in missing:
        full = src_links.get(t, f"[[{t}]]")
        mm = LINK_RE.match(full)
        label = mm.group(2) if mm and mm.group(2) else t
        lines.append(f"- [[{t}]] {label}")
    lines += ["", rules, "", body_label, "", draft]
    return "\n".join(lines)


def _relabel_once(draft: str, missing: list[str], src_links: dict[str, str], lang: str,
                  max_tokens: int) -> str:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": _relabel_prompt(draft, missing, src_links, lang)}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if SUPPRESS_REASONING:
        payload["thinking"] = {"type": "disabled"}
    resp = _http_json(payload, timeout=600)
    content = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return content.strip() if content else ""


def _write(fm_text: str, body: str, path: Path) -> None:
    path.write_text(fm_text + body.rstrip("\n") + "\n", encoding="utf-8")


def _log_resume(rel: str, ok: bool, sha: str, error: str | None = None) -> None:
    rec = {"key": rel, "ok": ok, "sha": sha, "when": _now()}
    if error:
        rec["error"] = error
    with open(_resume_log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Ripara i wikilink nelle traduzioni del vault.")
    ap.add_argument("--vault", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--only", action="append", default=[], metavar="SUBSTRING",
                    help="Processa solo file il cui percorso contiene SUBSTRING "
                         "(case-insensitive, ripetibile)")
    ap.add_argument("--shard", default=None, metavar="K/N",
                    help="Processa solo lo shard K di N (distribuzione per hash "
                         "del percorso; per passate parallele su worker distinti)")
    ap.add_argument("--only-drift", action="store_true",
                    help="Processa solo i file il cui ultimo record resume ha ok=false "
                         "(richiede --force)")
    args = ap.parse_args()

    if args.only_drift and not args.force:
        raise SystemExit("--only-drift richiede --force (riprocessa i file in drift)")

    shard = None
    if args.shard:
        try:
            k, n = (int(x) for x in args.shard.split("/", 1))
        except ValueError:
            raise SystemExit(f"--shard deve essere K/N (es. 0/8): {args.shard!r}")
        if n < 1 or not (0 <= k < n):
            raise SystemExit(f"--shard invalido: K in [0,N), N >= 1: {args.shard!r}")
        shard = (k, n)

    vault = Path(args.vault) if args.vault else Path(__file__).resolve().parents[3] / "VaultPhilosophy"
    if not vault.is_dir():
        raise SystemExit(f"Vault non trovato: {vault}")

    global _resume_log_path
    _resume_log_path = vault.parent / "data" / "ds_links_resume.jsonl"

    valid_ids = load_taxonomy_ids(Path(__file__).resolve().parents[2] / "data" / "taxonomy.json")
    only = [s.lower() for s in args.only]

    resume: dict[str, dict] = {}
    if _resume_log_path.is_file():
        for line in _resume_log_path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                resume[rec["key"]] = rec
            except (json.JSONDecodeError, KeyError):
                pass

    # ---- SCAN ----
    files = []  # (rel, tr_path, src_path)
    orphans = 0
    for root, _, names in os.walk(vault):
        for name in names:
            if not (name.endswith(".it.md") or name.endswith(".en.md")):
                continue
            tr = Path(root) / name
            src = Path(root) / (name[:-6] + ".md")
            rel = str(tr.relative_to(vault.parent))
            if only and not any(s in rel.lower() for s in only):
                continue
            if shard:
                k, n = shard
                h = int(hashlib.sha256(rel.encode("utf-8")).hexdigest(), 16)
                if h % n != k:
                    continue
            if not src.is_file():
                orphans += 1
                continue
            files.append((rel, tr, src))
    files.sort()

    stats = {
        "scanned": 0, "phase1_only": 0, "phase2_only": 0, "both": 0,
        "nothing": 0, "resume_skip": 0, "drift": 0, "api_calls": 0,
        "stripped": 0, "restored": 0, "unlabeled": 0,
        "repaired": 0, "relabeled": 0,
    }
    drifts: list[tuple[str, list[str]]] = []
    pending = []  # (rel, tr, fm_text, body1, removed, need, expected, src_links, src_pos, src_counts)

    for rel, tr, src in files:
        stats["scanned"] += 1
        rec = resume.get(rel)
        if args.only_drift and not (rec and rec.get("ok") is False):
            continue
        try:
            raw = tr.read_text(encoding="utf-8")
            src_raw = src.read_text(encoding="utf-8")
        except Exception:
            continue
        m = FM_RE.match(raw)
        fm_text = m.group(0) if m else ""
        body = raw[m.end():] if m else raw

        src_links = extract_links(src_raw)
        src_targets = set(src_links.keys())
        src_counts = link_counts(src_raw)
        body1, removed = phase1_fix(body, src_targets, valid_ids, src_counts)

        sha = _sha(body1)
        if rec and rec.get("sha") == sha and not args.force:
            stats["resume_skip"] += 1
            continue

        expected = src_targets & valid_ids
        trans_counts = link_counts(body1)
        missing = sorted(t for t in expected if trans_counts.get(t, 0) < src_counts[t])
        need = {t: src_counts[t] - trans_counts.get(t, 0) for t in missing}

        pos = link_positions(src_raw)
        src_pos = {t: pos.get(t, 0) for t in missing}

        stats["unlabeled"] += _count_unlabeled(body, valid_ids)

        if not missing and removed == 0:
            stats["nothing"] += 1
            continue

        pending.append((rel, tr, fm_text, body1, removed, need,
                        expected, src_links, src_pos, src_counts))

    # ---- REPORT ----
    print("=" * 70, file=sys.stderr)
    print(f"VAULT: {vault}", file=sys.stderr)
    print(f"Modello fase 2: {MODEL}", file=sys.stderr)
    if only:
        print(f"Filtro --only: {args.only}", file=sys.stderr)
    if shard:
        print(f"Shard: {shard[0]}/{shard[1]}", file=sys.stderr)
    if args.only_drift:
        print("Filtro --only-drift: solo file in drift", file=sys.stderr)
    print(f"File esaminati: {stats['scanned']}  (orfani senza fonte: {orphans})", file=sys.stderr)
    print(f"  gia' processati (resume): {stats['resume_skip']}", file=sys.stderr)
    print(f"  nessun intervento:        {stats['nothing']}", file=sys.stderr)
    print(f"  link senza etichetta (info): {stats['unlabeled']}", file=sys.stderr)
    print(f"  DA PROCESSARE:            {len(pending)}", file=sys.stderr)
    print("-" * 70, file=sys.stderr)

    if args.dry_run:
        for rel, tr, fm_text, body1, removed, need, expected, src_links, src_pos, src_counts in pending:
            what = []
            if removed:
                what.append(f"rimuovi {removed} link inventati")
            if need:
                what.append(f"ripristina {sum(need.values())}: {sorted(need)}")
            print(f"  [dry] {rel}: {', '.join(what)}", file=sys.stderr)
        print(f"\n[dry-run] Nessun file scritto, nessuna chiamata API.", file=sys.stderr)
        return

    # ---- APPLICA ----
    idx = 0
    for rel, tr, fm_text, body1, removed, need, expected, src_links, src_pos, src_counts in pending:
        idx += 1
        lang = "it" if rel.endswith(".it.md") else "en"
        missing = sorted(need)

        if not missing:
            _write(fm_text, body1, tr)
            _log_resume(rel, ok=True, sha=_sha(body1))
            stats["phase1_only"] += 1
            stats["stripped"] += removed
            print(f"[{idx}] {rel}: rimossi {removed} link inventati", file=sys.stderr)
            continue

        print(f"[{idx}] {rel}: mancano {missing} ", end="", file=sys.stderr)
        resp = None
        last_err = None
        relabel_draft = None
        for attempt in range(3):
            try:
                resp = _restore_once(body1, need, src_links, lang, args.max_tokens)
                stats["api_calls"] += 1
            except Exception as e:
                last_err = e
                resp = None
                print(f"API error (tentativo {attempt + 1}): {e} ", end="", file=sys.stderr)
            if resp:
                if _verify(resp, body1, expected, src_counts):
                    break
                if relabel_draft is None and _needs_relabel(resp, valid_ids):
                    relabel_draft = resp
                fixed = _repair_links(resp, body1, expected, valid_ids, src_pos, src_counts)
                if fixed is not None:
                    resp = fixed
                    stats["repaired"] += 1
                    break
                print(f"verifica fallita (tentativo {attempt + 1}) ", end="", file=sys.stderr)
                resp = None
            time.sleep(args.sleep)

        if not resp and relabel_draft is not None:
            for attempt in range(2):
                try:
                    resp = _relabel_once(relabel_draft, missing, src_links, lang,
                                         args.max_tokens)
                    stats["api_calls"] += 1
                except Exception as e:
                    last_err = e
                    resp = None
                    print(f"API error relabel (tentativo {attempt + 1}): {e} ",
                          end="", file=sys.stderr)
                if resp:
                    if _verify(resp, body1, expected, src_counts):
                        stats["relabeled"] += 1
                        break
                    print(f"relabel fallito (tentativo {attempt + 1}) ",
                          end="", file=sys.stderr)
                    resp = None
                time.sleep(args.sleep)

        if resp:
            _write(fm_text, resp, tr)
            _log_resume(rel, ok=True, sha=_sha(resp))
            if removed:
                stats["both"] += 1
                stats["stripped"] += removed
            else:
                stats["phase2_only"] += 1
            stats["restored"] += sum(need.values())
            print(f"OK (ripristinati {sum(need.values())})", file=sys.stderr)
        else:
            if removed:
                _write(fm_text, body1, tr)
                stats["stripped"] += removed
            stats["drift"] += 1
            drifts.append((rel, missing))
            _log_resume(rel, ok=False, sha=_sha(body1), error="drift")
            reason = f"ultimo errore: {last_err}" if last_err else "verifica non superata"
            print(f"DRIFT ({reason})", file=sys.stderr)
        time.sleep(args.sleep)

    # ---- RIEPILOGO ----
    print("=" * 70, file=sys.stderr)
    print(f"File esaminati:        {stats['scanned']}", file=sys.stderr)
    print(f"Gia' processati:       {stats['resume_skip']}", file=sys.stderr)
    print(f"Nessun intervento:     {stats['nothing']}", file=sys.stderr)
    print(f"Fase 1 sola:           {stats['phase1_only']}  (link inventati rimossi: {stats['stripped']})",
          file=sys.stderr)
    print(f"Fase 2 sola:           {stats['phase2_only']}", file=sys.stderr)
    print(f"Entrambe:              {stats['both']}", file=sys.stderr)
    print(f"Target ripristinati:   {stats['restored']}", file=sys.stderr)
    print(f"Target riparati (euristica):   {stats['repaired']}", file=sys.stderr)
    print(f"Etichette corrette (LLM):      {stats['relabeled']}", file=sys.stderr)
    print(f"Drift (non risolti):   {stats['drift']}", file=sys.stderr)
    print(f"Chiamate API:          {stats['api_calls']}", file=sys.stderr)
    for rel, missing in drifts:
        print(f"  DRIFT {rel}: persi {missing}", file=sys.stderr)
    if not drifts:
        print("  (nessun drift)", file=sys.stderr)
    print("=" * 70, file=sys.stderr)


if __name__ == "__main__":
    main()
