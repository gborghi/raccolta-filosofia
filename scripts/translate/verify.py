"""Verifica gli atomi tradotti (`*.it.md` e `*.en.md`) contro le loro fonti.

Uso:
    python scripts/translate/verify.py [--vault PATH] [--quiet]

Esce 1 se una traduzione è agganciata all'atomo sbagliato, ha una struttura a
blocchi diversa dalla fonte, o (solo per `.it.md`) contiene blocchi lasciati in
inglese.

Le regole stanno in scripts/translate/REGOLE.md.
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VAULT = os.path.normpath(os.path.join(HERE, "..", "..", "..", "VaultPhilosophy"))

FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.S)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]")
H1_RE = re.compile(r"^([ \t]*\r?\n)*[ \t]*#[ \t]+(.+?)[ \t]*$", re.M)

# Un blocco è prosa se contiene una parola vera: così i separatori e le righe di
# soli segni non entrano nel conteggio, che altrimenti dipenderebbe da quante
# righe vuote ha lasciato il traduttore invece che dalla struttura del testo.
WORD_RE = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

EN_STOP = {
    "the", "of", "and", "to", "that", "which", "with", "is", "are", "was",
    "were", "this", "these", "those", "from", "have", "has", "had", "not",
    "but", "for", "his", "her", "their", "them", "they", "there", "would",
    "when", "what", "who", "been", "into", "than", "then", "shall", "upon",
}
IT_STOP = {
    "il", "lo", "la", "i", "gli", "le", "di", "del", "della", "dei", "delle",
    "che", "chi", "cui", "un", "uno", "una", "per", "con", "non", "sono",
    "era", "erano", "questo", "questa", "questi", "queste", "quello", "quella",
    "da", "dal", "dalla", "nel", "nella", "come", "anche", "più", "essere",
    "ha", "hanno", "aveva", "ma", "se", "si", "suo", "sua", "loro", "quando",
}


def parse_fm(text):
    """Frontmatter -> dict. Solo `key: value` piatto, che è tutto ciò che l'atomo usa."""
    m = FM_RE.match(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        fm[k.strip()] = v
    return fm, text[m.end():]


def prose_blocks(body):
    return [b for b in re.split(r"\n[ \t]*\n", body) if WORD_RE.search(b)]


def looks_english(block):
    """True se il blocco è plausibilmente rimasto in inglese.

    Volutamente conservativa: molte parole inglesi E nessuna italiana. Un blocco
    italiano con una citazione inglese dentro ha comunque le sue funzionali
    italiane e non viene segnalato — meglio mancare un residuo che bloccare il
    build su un falso positivo.
    """
    toks = [t.lower() for t in TOKEN_RE.findall(block)]
    if len(toks) < 12:
        return False
    en = sum(1 for t in toks if t in EN_STOP)
    it = sum(1 for t in toks if t in IT_STOP)
    return en >= 5 and it == 0


def check(tr_path):
    """Ritorna la lista dei problemi (stringhe) di una traduzione `.it.md`/`.en.md`."""
    if tr_path.endswith(".it.md"):
        want_lang = "it"
    elif tr_path.endswith(".en.md"):
        want_lang = "en"
    else:
        return ["suffisso non riconosciuto (atteso .it.md o .en.md)"]

    src_path = tr_path[: -len(f".{want_lang}.md")] + ".md"
    if not os.path.exists(src_path):
        return ["nessun atomo sorgente accanto (sibling .md mancante)"]

    with open(src_path, encoding="utf-8") as fh:
        src_fm, src_body = parse_fm(fh.read())
    with open(tr_path, encoding="utf-8") as fh:
        tr_fm, tr_body = parse_fm(fh.read())

    problems = []

    if tr_fm.get("lang") != want_lang:
        problems.append(f'lang e\' {tr_fm.get("lang")!r}, atteso "{want_lang}"')
    # work/atom_n sono le chiavi che legano la traduzione al suo atomo: se
    # sbagliano, il testo tradotto finisce sotto un altro brano e nessun
    # controllo a valle se ne accorge.
    for key in ("philosopher", "work", "atom_n"):
        if str(tr_fm.get(key, "")) != str(src_fm.get(key, "")):
            problems.append(
                f"{key}: {tr_fm.get(key)!r} != {src_fm.get(key)!r} della fonte"
            )

    src_blocks, tr_blocks = prose_blocks(src_body), prose_blocks(tr_body)
    if len(src_blocks) != len(tr_blocks):
        problems.append(f"{len(tr_blocks)} blocchi contro {len(src_blocks)} della fonte")

    if H1_RE.match(src_body.lstrip("\n")) and not H1_RE.match(tr_body.lstrip("\n")):
        problems.append("manca l'H1 che la fonte ha")

    # I bersagli dei wikilink sono ID canonici: se il traduttore ne traduce uno
    # ("[[consuetudine|...]]" invece di "[[custom|...]]") il link punta al vuoto e
    # il nodo perde la pagina tradotta. Il confronto e' sui bersagli, non sulle
    # etichette — quelle *devono* cambiare.
    src_targets = [m.group(1).strip() for m in WIKILINK_RE.finditer(src_body)]
    tr_targets = [m.group(1).strip() for m in WIKILINK_RE.finditer(tr_body)]
    if src_targets != tr_targets:
        missing = sorted(set(src_targets) - set(tr_targets))
        added = sorted(set(tr_targets) - set(src_targets))
        detail = []
        if missing:
            detail.append(f"persi {missing}")
        if added:
            detail.append(f"inventati {added}")
        if not detail:
            detail.append("stesso insieme ma ordine/numero diversi")
        problems.append("wikilink: " + ", ".join(detail))

    # Un'etichetta identica alla fonte su ogni link e' il sintomo di chi ha
    # copiato i wikilink invece di tradurli.
    untranslated_labels = [
        m.group(1)
        for m in WIKILINK_RE.finditer(tr_body)
        if m.group(2) is None
    ]
    if untranslated_labels:
        problems.append(
            f"wikilink senza etichetta (usare [[id|testo]]): {untranslated_labels}"
        )

    if tr_body.strip() == src_body.strip():
        problems.append("identico alla fonte (non tradotto)")
    elif want_lang == "it":
        # L'euristica del residuo inglese vale solo verso l'italiano: un `.en.md`
        # e' inglese per definizione.
        left = [i for i, b in enumerate(tr_blocks) if looks_english(b)]
        if left:
            problems.append(f"blocchi ancora in inglese: {left}")

    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    tr_files = []
    for root, _, names in os.walk(args.vault):
        tr_files.extend(
            os.path.join(root, n)
            for n in names
            if n.endswith(".it.md") or n.endswith(".en.md")
        )
    tr_files.sort()

    bad = 0
    for p in tr_files:
        problems = check(p)
        if problems:
            bad += 1
            rel = os.path.relpath(p, args.vault)
            print(f"FAIL {rel}")
            for pr in problems:
                print(f"     - {pr}")

    ok = len(tr_files) - bad
    if not args.quiet or bad:
        print(f"\n{len(tr_files)} tradotti: {ok} ok, {bad} da correggere")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
