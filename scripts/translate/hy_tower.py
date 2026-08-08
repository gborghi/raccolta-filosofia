# -*- coding: utf-8 -*-
"""Motore di traduzione degli atomi con HY-MT (LM Studio :1234).

Porta la meccanica gia' provata in ../English (`dickens_tower.py` +
`run_dickens_hy.py`) con le tre differenze che il vault di filosofia impone:

  * **Bidirezionale.** Le fonti sono `en`/`fr`/`de`/`es`/`la`/`grc`: ogni atomo va
    reso in italiano *e* in inglese (mai nella propria lingua), e ciascuna
    traduzione si fa **direttamente dall'originale**. Mai a cascata
    originale -> EN -> IT: sommerebbe le derive di due passaggi (REGOLE.md).
  * **I bersagli dei wikilink sono ID canonici.** Il mascheramento `[[Lnn|label]]`
    non e' un'ottimizzazione ma l'invariante del progetto: `[[custom|CUSTOM]]`
    deve diventare `[[custom|CONSUETUDINE]]`, mai `[[consuetudine|...]]`.
  * **Un link perso non e' fatale, un link inventato si'** — come in English. Un
    bersaglio inventato punterebbe a un nodo inesistente e va rifiutato; un
    bersaglio *perso* lascia la pagina perfettamente pubblicabile, solo con meno
    link concettuali, e ributtare via l'intera traduzione per quello significa non
    tradurre mai gli atomi piu' densi. I persi finiscono in
    `data/hy_linkfix.jsonl` per una passata di riparazione sul testo tradotto:
    riattaccare markup dopo costa poco, ritradurre alla cieca no.

**Conseguenza da conoscere:** `verify.py` confronta la lista *ordinata* dei
bersagli, quindi segnalera' come da correggere proprio gli atomi con link persi.
E' voluto: quell'elenco *e'* la coda di riparazione (in English e' il lavoro #21,
40.320 link mai riagganciati). Non e' un test rotto, e' un arretrato misurato.

Richiede LM Studio su :1234 con `hy-mt1.5-7b` caricato.
"""
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify  # noqa: E402  -- unica fonte di verita' per la validazione

ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))          # quartz-philosophy/
VAULT_ROOT = os.path.normpath(os.path.join(ROOT, "..", "VaultPhilosophy"))
PHIL_DIR = os.path.join(VAULT_ROOT, "Philosophers")
LOG_DIR = os.path.join(HERE, "run_logs")

HOST = os.environ.get("LMSTUDIO_HOST", "http://localhost:1234")
MODEL = os.environ.get("HY_MODEL", "hy-mt1.5-7b")

LANG_NAMES = {
    "it": "Italian", "en": "English", "fr": "French", "de": "German",
    "es": "Spanish", "la": "Latin", "grc": "Ancient Greek", "pt": "Portuguese",
}

# I sibling di lingua non sono atomi: `NNN_slug.it.md` e' lo stesso atomo in
# un'altra lingua. Ogni camminata sul corpus deve filtrarli, o conta piu' volte
# lo stesso testo e mescola il latino nel campione inglese.
SIBLING_RE = re.compile(r"\.[a-z]{2,3}\.md$")
CONFLICTED_RE = re.compile(r" \([^()]*conflicted copy \d{4}-\d{2}-\d{2}\)")


# --------------------------------------------------------------------------
# lettura/scrittura degli atomi
# --------------------------------------------------------------------------
FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.S)


def read_atom(path):
    """(frontmatter dict, corpo) di un atomo. Riusa il parser di verify.py."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return verify.parse_fm(text)


def build_fm(src_fm, tgt_lang):
    """Frontmatter ridotto della traduzione (REGOLE.md).

    Solo le chiavi che legano la traduzione al suo atomo. `edizione`,
    `traduttore` e `pd_year` descrivono l'edizione *di partenza*: ripeterli qui
    attribuirebbe il testo tradotto al traduttore di quella edizione.
    """
    out = ["---"]
    out.append('philosopher: "%s"' % src_fm.get("philosopher", ""))
    out.append('lang: "%s"' % tgt_lang)
    out.append('work: "%s"' % src_fm.get("work", ""))
    out.append("atom_n: %s" % src_fm.get("atom_n", ""))
    out.append("---")
    return "\n".join(out) + "\n"


def needed_langs(src_lang):
    """Quali sibling servono, data la lingua della fonte (tabella di REGOLE.md)."""
    return tuple(l for l in ("it", "en") if l != src_lang)


def sibling_path(src_path, lang):
    return src_path[:-3] + "." + lang + ".md"


# --------------------------------------------------------------------------
# wikilink: mascheramento e ripristino
# --------------------------------------------------------------------------
# Un wikilink non attraversa mai un a capo: escludendo \n da entrambi i gruppi,
# un `[[` non chiuso non ingoia in avanti fino al `]]` successivo mangiandosi il
# link vero che sta in mezzo.
WIKILINK_RE = re.compile(r"\[\[([^\]|\n]+)(?:\|([^\]\n]*))?\]\]")
CODE_RE = re.compile(r"\[\[(L\d{2,})\|([^\]]*)\]\]")


def mask_links(block):
    """`[[bersaglio|etichetta]]` -> `[[Lnn|etichetta]]`; `[[Parola]]` -> `[[Lnn|Parola]]`.

    I bersagli sono ID del vocabolario controllato, cioe' parole vere che il
    traduttore "utilmente" rende nella lingua d'arrivo, rompendo il link. Un
    codice `Lnn` non ha nulla da tradurre: sopravvive, e il bersaglio vero si
    rimette dopo.
    """
    targets = []

    def sub(m):
        target, label = m.group(1), m.group(2)
        targets.append(target)
        return "[[L%02d|%s]]" % (len(targets), label if label is not None else target)

    return WIKILINK_RE.sub(sub, block), targets


def unmask_links(tr_block, targets):
    """`[[Lnn|etichetta]]` -> `[[bersaglio|etichetta]]`, **sempre nella forma con pipe**.

    Qui, a differenza di English, non si emette mai il `[[bersaglio]]` nudo
    quando l'etichetta coincide col bersaglio: `verify.py` segnala come errore
    ogni wikilink senza etichetta nella traduzione, perche' e' il sintomo di chi
    ha copiato i link invece di tradurli.
    """
    def sub(m):
        idx = int(m.group(1)[1:]) - 1
        label = m.group(2).strip()
        if idx < 0 or idx >= len(targets):
            return m.group(0)          # codice ignoto: lo prende validate()
        return "[[%s|%s]]" % (targets[idx], label or targets[idx])

    return CODE_RE.sub(sub, tr_block)


def codes_of(text):
    return [g[0] for g in CODE_RE.findall(text)]


def link_targets(text):
    """Lista ORDINATA dei bersagli, come la legge verify.py."""
    return [m.group(1).strip() for m in verify.WIKILINK_RE.finditer(text)]


# --- riparazione dei codici che il modello storpia -------------------------
# Accetta separatore sbagliato o assente, una sola quadra di chiusura, e le
# forme a larghezza piena 【】［］｜＞： al posto di quelle ASCII: HY e' un modello
# addestrato sul cinese e ci casca. Senza questa normalizzazione unmask non
# rimappa il codice, la `Lnn` sopravvive nel corpo e l'atomo viene rifiutato --
# e' l'intera classe di scarti "leftover mask token".
MALFORMED_CODE_RE = re.compile(
    r"(?:\[\[|【)(L\d{2,})\s*[|>:｜＞：\]］】]?\s*([^\[\]|｜【】［］]+?)\s*[\]］】]{1,2}")
# Quando il link mascherato chiude una citazione, il modello a volte chiude con
# la virgoletta invece che con la quadra. La virgoletta e' CONTENUTO: si
# reinserisce il `]]` davanti e la si lascia dov'e'.
UNCLOSED_CODE_RE = re.compile(
    r"(?:\[\[|【)(L\d{2,})\s*[|>:｜＞：\]］】]?\s*([^\[\]|｜【】［］\u201c\u201d«»\n]{1,60}?)\s*(?=[\u201d»])")
ANY_CODE_RE = re.compile(r"\[\[L\d{2,}\|?([^\]|]*)\]\]")
POISONED_RE = re.compile(r"\[\[L\d{1,3}\b")


def _unclosed_code(m):
    tail = m.string[m.end():m.end() + 8]
    if "]" in tail or "］" in tail or "】" in tail:
        return m.group(0)              # gia' chiuso subito dopo la virgoletta
    label = m.group(2)
    trimmed = label.rstrip(" ,;:!?.\u2019\u2018")
    if not trimmed:
        return m.group(0)
    return "[[%s|%s]]%s" % (m.group(1), trimmed, label[len(trimmed):])


def drop_stray_close(text):
    """Toglie un `]]` che sulla sua riga non ha nessun `[[` aperto.

    Conta la profondita' sull'INTERO testo, mai per riga: un'etichetta puo'
    legittimamente scavalcare un a capo, e il conteggio per riga leggerebbe la
    sua chiusura come orfana. Contare globalmente e' anche il modo giusto di
    sbagliare: un `[[` non chiuso prima tiene la profondita' sopra zero, quindi
    si manca un'orfana invece di mangiare una quadra buona.
    """
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


def repair_mask_codes(text):
    """Normalizza ogni codice storpiato a `[[Lnn|etichetta]]`, PRIMA di smascherare."""
    text = MALFORMED_CODE_RE.sub(r"[[\1|\2]]", text)
    text = UNCLOSED_CODE_RE.sub(_unclosed_code, text)
    return drop_stray_close(text)      # per ultima: le altre possono chiudere quadre


def strip_mask_codes(text):
    """Rete di sicurezza: riduce un codice residuo alla sola parola visibile, cosi'
    una fuga non puo' mai pubblicare un bersaglio inesistente `Lnn...`."""
    return ANY_CODE_RE.sub(lambda m: m.group(1), text)


# --- fughe CJK -------------------------------------------------------------
CJK_RE = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff01-\uff60]")
HAN_RANGES = "\u3400-\u4dbf\u4e00-\u9fff"
# HY rende il "half-" dei composti col carattere Han isolato U+534A. Va riparato,
# non rifiutato: a temperatura 0 il retry rigenera lo stesso carattere, quindi
# l'atomo si bloccherebbe per sempre senza mai ottenere la traduzione.
HALF_LEAK_RE = re.compile("[ \\t]*(?<![" + HAN_RANGES + "])\u534a(?![" + HAN_RANGES + "])[ \\t]*")


def cjk_leak(src, tr):
    """Caratteri CJK presenti nella traduzione e assenti dalla fonte."""
    return sorted(set(CJK_RE.findall(tr)) - set(CJK_RE.findall(src)))


def repair_half_leak(s):
    s = HALF_LEAK_RE.sub(" semi-", s)
    # la sostituzione antepone sempre uno spazio: va tolto dove e' finito a inizio
    # riga, o la riparazione sposterebbe il testo sulla riga precedente.
    return re.sub(r"(?m)^ semi-", "semi-", s)


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?;:])\s+|\n")
_MARKER_RE = re.compile(r"\[\[[^\[\]]*\]\]|\[\[L\d{1,3}\b")


def repair_cjk_span(s, tgt_lang, ask=None):
    """Ritraduce le sole frasi dove e' sopravvissuta una sequenza Han.

    Ultima istanza, e nient'altro: gira solo su un blocco che `cjk_leak()`
    butterebbe via comunque, quindi il suo caso peggiore (una frase un po'
    lasca) resta strettamente meglio di un atomo che non viene mai tradotto.
    Tutto cio' che non riesce a verificare lo lascia stare, cosi' la guardia
    rifiuta lo stesso.
    """
    if not CJK_RE.search(s):
        return s
    lang = LANG_NAMES.get(tgt_lang, tgt_lang)
    system = (
        "You are a literary translator. I give you a sentence in %s in which one or "
        "more words were left in Chinese. Rewrite the WHOLE sentence in correct %s, "
        "translating the Chinese words and respecting gender and number agreement. "
        "Add nothing, remove nothing, and leave every marker between double square "
        "brackets untouched. Answer with the sentence only." % (lang, lang)
    )
    ask = ask or (lambda t: call_hy([{"role": "system", "content": system},
                                     {"role": "user", "content": t}], 400))
    out = []
    for piece in re.split(r"(\n)", s):
        if piece == "\n" or not CJK_RE.search(piece):
            out.append(piece)
            continue
        parts = _SENT_SPLIT_RE.split(piece)
        rebuilt, cursor = [], 0
        for sent in parts:
            start = piece.find(sent, cursor)
            gap = piece[cursor:start] if start >= 0 else ""
            cursor = (start + len(sent)) if start >= 0 else cursor
            rebuilt.append(gap)
            rebuilt.append(_repair_one_sentence(sent, ask))
        rebuilt.append(piece[cursor:])
        out.append("".join(rebuilt))
    return "".join(out)


def _repair_one_sentence(sent, ask):
    if not CJK_RE.search(sent) or not sent.strip():
        return sent
    try:
        fixed = ask(sent).strip()
    except Exception:
        return sent
    # ogni guardia qui sotto e' una ragione per TENERE la frase rotta: una
    # riparazione che non sappiamo verificare non va contrabbandata in cache.
    if not fixed or CJK_RE.search(fixed):
        return sent
    if sorted(_MARKER_RE.findall(fixed)) != sorted(_MARKER_RE.findall(sent)):
        return sent
    if not 0.4 <= len(fixed) / max(1, len(sent)) <= 2.5:
        return sent
    if sent[:1].islower() and fixed[:1].isupper():
        fixed = fixed[:1].lower() + fixed[1:]
    return fixed


# --- puntini di sospensione ------------------------------------------------
def strip_ellipses(s):
    """HY aggiunge di suo il carattere di ellissi: nessun prompt lo ferma."""
    s = s.replace("...", "\u2026")
    s = re.sub(r"\s*\u2026\s*$", ".", s, flags=re.M)
    s = re.sub(r"\s*\u2026\s+(?=[A-Z\u00c0-\u00de\[\"«])", ". ", s)
    s = re.sub(r"\s*\u2026\s*", ", ", s)
    s = re.sub(r"\s+([.,;:!?])", r"\1", s)
    s = re.sub(r",\s*\.", ".", s)
    return s


# --------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------
def sha(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _corrupt_block(src, tr):
    """Blocco inservibile? Serve sia a rifiutare sia a NON servirlo dalla cache.

    Volutamente stretto: solo i difetti che rompono il markup o lasciano il testo
    fuori lingua. Un blocco semplicemente tradotto male non e' affare di questa
    funzione — deve restare cacheabile, o ogni run rifarebbe tutto da capo.
    """
    if POISONED_RE.search(tr):
        return True
    if cjk_leak(src, tr):
        return True
    if abs(tr.count("[[") - tr.count("]]")) > 0 and src.count("[[") == src.count("]]"):
        return True
    return False


class Cache(object):
    """sha1(lingua + blocco fonte) -> blocco tradotto, in append.

    Consapevole del veleno: una voce con un codice `Lnn` residuo o del CJK fuggito
    e' trattata come miss in lettura e sovrascritta in scrittura. Conta piu' di
    quanto sembri: una cache davanti a una riparazione la disattiva in silenzio,
    ed e' esattamente cosi' che in English l'epidemia dei mask token e'
    sopravvissuta a tre correzioni successive.
    """

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
                            continue   # riga troncata da un kill: si scarta
                        self.d[r["h"]] = r["tr"]
        self._fh = open(path, "a", encoding="utf-8")

    def _key(self, s, lang):
        return sha(lang + "\x00" + s)

    def get(self, s, lang):
        with self._lock:
            tr = self.d.get(self._key(s, lang))
        if tr is not None and _corrupt_block(s, tr):
            return None
        return tr

    def put(self, s, lang, tr):
        h = self._key(s, lang)
        with self._lock:
            if h in self.d and not _corrupt_block(s, self.d[h]):
                return
            self.d[h] = tr
            self._fh.write(json.dumps({"h": h, "lang": lang, "src": s, "tr": tr},
                                      ensure_ascii=False) + "\n")
            self._fh.flush()


# --------------------------------------------------------------------------
# chiamata al modello
# --------------------------------------------------------------------------
def call_hy(messages, max_tokens, retries=3, temperature=0):
    body = json.dumps({"model": MODEL, "temperature": temperature,
                       "max_tokens": max_tokens, "messages": messages}).encode("utf-8")
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(HOST + "/v1/chat/completions", data=body,
                                         headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=900).read())
            out = r["choices"][0]["message"]["content"].strip()
            if out:
                return out
            last = "empty completion"
        except Exception as e:          # singhiozzi transitori del motore
            last = repr(e)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("HY call failed: %s" % last)


# La convenzione `[[Lxx|parola]]` si insegna per ESEMPIO, non per regola: HY e' un
# modello MT specializzato, ignora la prosa normativa ma ricalca i pattern. In
# English questo ha portato la conservazione dei link da 11/17 a ~15/17.
_FEWSHOT = {
    "it": [
        {"role": "user", "content": "Translate to Italian:\n\nThe boys were paralysed "
            "with [[L01|wonder]]; the young [[L02|rebel]] felt no [[L03|fear]]."},
        {"role": "assistant", "content": "I ragazzi erano paralizzati dallo "
            "[[L01|stupore]]; il giovane [[L02|ribelle]] non provava alcuna [[L03|paura]]."},
        {"role": "user", "content": "Translate to Italian:\n\nWe are determined by "
            "[[L01|CUSTOM]] alone to suppose the future conformable to the past."},
        {"role": "assistant", "content": "Siamo determinati dalla sola "
            "[[L01|CONSUETUDINE]] a supporre il futuro conforme al passato."},
    ],
    "en": [
        {"role": "user", "content": "Translate to English:\n\nLes gar\u00e7ons \u00e9taient "
            "paralys\u00e9s par l'[[L01|\u00e9tonnement]] ; le jeune [[L02|rebelle]] "
            "n'\u00e9prouvait aucune [[L03|peur]]."},
        {"role": "assistant", "content": "The boys were paralysed with [[L01|wonder]]; "
            "the young [[L02|rebel]] felt no [[L03|fear]]."},
        {"role": "user", "content": "Translate to English:\n\nDer [[L01|Wille]] ist das "
            "Ding an sich, und die [[L02|Vorstellung]] ist nur seine Erscheinung."},
        {"role": "assistant", "content": "The [[L01|will]] is the thing in itself, and "
            "the [[L02|representation]] is only its appearance."},
    ],
}


def _system(tgt_lang, has_links):
    lang = LANG_NAMES.get(tgt_lang, tgt_lang)
    s = ("You are a literary translator of philosophical prose, rendering the text "
         "into %s. Preserve the author's register: do not modernise, do not soften, "
         "do not explain. Add no notes, no preface, no commentary. Keep every "
         "sentence whole and return exactly ONE paragraph with no blank lines. "
         "Punctuation: only . , ; : ! ? and quotes; NEVER output the ellipsis "
         "character. Output ONLY the %s translation." % (lang, lang))
    if has_links:
        s += (" Every [[Lxx|word]] marker MUST reappear EXACTLY as [[Lxx|translated]]: "
              "keep the Lxx code, keep the vertical bar '|' (never ']' nor a space), "
              "translate ONLY the word after '|'. Never drop a marker, never flatten "
              "it to plain text, never reorder the markers.")
    return s


def _ask(masked_text, tgt_lang, src_lang, want, temperature=0):
    """Una chiamata su testo gia' mascherato. Ritorna il testo tradotto grezzo."""
    msgs = [{"role": "system", "content": _system(tgt_lang, bool(want))}]
    msgs.extend(_FEWSHOT.get(tgt_lang, []))
    src_name = LANG_NAMES.get(src_lang, src_lang)
    msgs.append({"role": "user", "content": "Translate this %s passage to %s:\n\n%s"
                 % (src_name, LANG_NAMES.get(tgt_lang, tgt_lang), masked_text)})
    # Tetto proporzionale alla fonte. Dato un testo corto il modello smette di
    # tradurre e comincia a SCRIVERE: in English una riga di 30 caratteri e'
    # tornata come 13.759 caratteri di pastiche inventato. Le lingue romanze
    # corrono ~1,1-1,3x l'inglese, quindi len/1.4 lascia margine abbondante e
    # rende quella fabbricazione fisicamente impossibile.
    budget = min(4096, max(64, int(len(masked_text) / 1.4)))
    out = call_hy(msgs, budget, temperature=temperature)
    out = repair_mask_codes(out)
    out = repair_half_leak(out)
    out = repair_cjk_span(out, tgt_lang)
    out = strip_ellipses(out)
    # Un blocco non deve MAI contenere una riga vuota, o si spezzerebbe in due e
    # il conteggio dei blocchi divergerebbe dalla fonte.
    return re.sub(r"\s*\n[ \t]*\n+\s*", " ", out).strip()


# --------------------------------------------------------------------------
# lunghezza: fabbricazione e troncamento
# --------------------------------------------------------------------------
def is_fabricated(src_block, tr_block):
    """La traduzione e' troppo lunga per essere una traduzione.

    IL modo di fallire di questa pipeline. Struttura e link non lo vedono — il
    conteggio dei blocchi e i bersagli tornano perfetti — quindi la fabbricazione
    passerebbe la validazione e verrebbe pubblicata come parole dell'autore.
    Il doppio della fonte non e' piu' spazio per lo stesso senso: e' senso nuovo.
    """
    return len(tr_block) > 2 * len(src_block) + 80


def is_truncated(src_block, tr_block):
    """La traduzione e' troppo corta per essere una traduzione.

    L'immagine speculare, e il difetto che in English aveva davvero corrotto il
    vault: oltre il tetto di `max_tokens` il modello restituisce una frase o due
    e si ferma. Sotto la meta' della fonte non c'e' nessuna lettura del testo in
    cui il significato sia sopravvissuto. Il pavimento a 200 caratteri tiene
    fuori titoli e blocchi di una parola, dove i rapporti non significano nulla.
    """
    if len(src_block) < 200:
        return False
    return 2 * len(tr_block) + 80 < len(src_block)


# Due tetti indipendenti si incontrano qui: la chiamata tronca l'output, e HY
# degenera ben prima — dato un passo lungo restituisce una frase plausibile e si
# ferma. L'innesco e' il CONTENUTO, non la lunghezza, e a temperatura 0 e'
# deterministico: ritentare lo stesso testo e' inutile, solo una divisione
# diversa ne esce.
MAX_BLOCK_CHARS = 3000
RESPLIT_LADDER = (1200, 500)
_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def _chunk_oversized(block, limit=MAX_BLOCK_CHARS):
    """Divide un blocco troppo grande alla giuntura meno dannosa disponibile.

    Tradurre frase per frase distrugge la coesione che questa pipeline esiste per
    preservare, quindi non si spezza per principio. Ma quel compromesso esiste
    solo per i blocchi che il modello riesce davvero a tradurre: sopra il tetto
    la scelta non e' coesione contro spezzatura, e' spezzatura contro moncone.
    """
    if len(block) <= limit:
        return [block]
    pieces, buf = [], ""
    for line in block.split("\n"):
        if len(line) > limit:                     # un paragrafo sfora da solo
            if buf:
                pieces.append(buf)
                buf = ""
            sent = ""
            for s in _SENT_RE.split(line):
                if sent and len(sent) + len(s) + 1 > limit:
                    pieces.append(sent)
                    sent = s
                else:
                    sent = (sent + " " + s).strip()
            if sent:
                pieces.append(sent)
            continue
        if buf and len(buf) + len(line) + 1 > limit:
            pieces.append(buf)
            buf = line
        else:
            buf = (buf + "\n" + line) if buf else line
    if buf:
        pieces.append(buf)
    return pieces


def translate_block(src_block, tgt_lang, src_lang, tries=3):
    """Traduce un blocco, spezzandolo solo quanto il modello ci costringe.

    Ritorna `(testo, mancanti)`: `mancanti` sono i bersagli che il modello non ha
    ricollocato. Qui, a differenza di English, un mancante fara' rifiutare
    l'atomo — ma la decisione sta in `validate()`, non qui.
    """
    attempted_whole = False
    tr, missing = "", []
    for limit in (MAX_BLOCK_CHARS,) + RESPLIT_LADDER:
        chunks = _chunk_oversized(src_block, limit)
        if len(chunks) == 1:
            if attempted_whole:
                continue                          # nemmeno questo limite lo divide
            attempted_whole = True
            tr, missing = _translate_whole(src_block, tgt_lang, src_lang, tries)
        else:
            outs, missing = [], []
            for c in chunks:
                tr_c, miss_c = translate_block(c, tgt_lang, src_lang, tries)
                outs.append(tr_c)
                missing.extend(miss_c)
            tr = "\n".join(outs)
        if not is_truncated(src_block, tr):
            return tr, missing
    return tr, missing                            # esaurito: rifiutera' validate()


def _translate_whole(src_block, tgt_lang, src_lang, tries=3):
    """Traduce un blocco intero in UNA chiamata, cosi' il modello ha tutto il contesto."""
    masked, targets = mask_links(src_block)
    want = ["L%02d" % (i + 1) for i in range(len(targets))]

    if not want:
        out = ""
        for _ in range(tries):
            out = _ask(masked, tgt_lang, src_lang, want)
            # markup inventato dove la fonte non ne aveva: si appiattisce
            out = verify.WIKILINK_RE.sub(lambda m: m.group(2) or m.group(1), out)
            if not is_fabricated(src_block, out):
                return out, []
        raise RuntimeError("fabricated output: %d chars src -> %d chars %s"
                           % (len(src_block), len(out), tgt_lang))

    best, best_got = None, []
    for _ in range(tries):
        out = _ask(masked, tgt_lang, src_lang, want)
        if is_fabricated(src_block, out):
            continue                              # testo inventato: mai tenerlo
        got = codes_of(out)
        if got == want:
            return unmask_links(out, targets), [] # centro pieno
        if best is None or len(set(got) & set(want)) > len(set(best_got) & set(want)):
            best, best_got = out, got
        # Ritentare paga solo quando il modello c'e' andato vicino: un codice o due
        # alla deriva, e un altro campione spesso li ricolloca. Se torna ZERO
        # codici ha deciso che questo testo non vuole markup, e ricampionare a
        # temperatura 0 brucia secondi per riavere la stessa identica risposta.
        # I link mancanti vanno alla passata di riparazione comunque.
        if not got:
            break
    if best is None:
        raise RuntimeError("fabricated output on all %d tries (%d chars src)"
                           % (tries, len(src_block)))
    tr = unmask_links(best, targets)
    missing = [targets[int(c[1:]) - 1] for c in want if c not in best_got]
    return tr, missing


# --------------------------------------------------------------------------
# atomo intero
# --------------------------------------------------------------------------
PART_SPLIT_RE = re.compile(r"(\n[ \t]*\n)")
HEADING_RE = re.compile(r"\A([ \t]*#{1,6}[ \t]+)(.*)\Z", re.S)
# Il licence footer di Gutenberg non e' testo dell'autore e non va tradotto: i
# suoi frammenti a capo in mezzo alla frase spingono il modello a completarli,
# il che fa scattare la guardia sulla fabbricazione e uccide l'atomo intero.
BOILERPLATE_RE = re.compile(
    r"project gutenberg|gutenberg\.org|gutenberg-tm|www\.|https?://|archive foundation"
    r"|copyright royalt|electronic works?\b|redistribut|\brefund\b|\btrademark\b", re.I)


def translate_atom(src_path, tgt_lang, cache):
    """Corpo tradotto di un atomo. Ritorna `(corpo, mancanti)`.

    La segmentazione in blocchi e' la STESSA di `verify.prose_blocks` (split su
    riga vuota), e i separatori si conservano byte per byte: e' cosi' che il
    conteggio dei blocchi torna per costruzione invece che per fortuna.
    """
    src_fm, body = read_atom(src_path)
    src_lang = src_fm.get("lang", "en")
    parts = PART_SPLIT_RE.split(body)
    out, missing = [], []
    for k, part in enumerate(parts):
        if k % 2:                                  # separatore: verbatim
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
                # L'H1 si traduce ma non si rimuove, e i marcatori di livello
                # restano identici: verify.py controlla che la traduzione abbia
                # l'H1 dove ce l'ha la fonte.
                hashes, text = m.group(1), m.group(2)
                tr_text, miss = translate_block(text, tgt_lang, src_lang)
                tr = hashes + tr_text.lstrip()
            else:
                tr, miss = translate_block(s, tgt_lang, src_lang)
            missing.extend(miss)
            cache.put(s, tgt_lang, tr)
        tr = strip_mask_codes(tr)                  # rete: nessun codice residuo esce
        # si conserva lo spazio attorno al blocco, cosi' la ricucitura e' fedele
        lead = part[:len(part) - len(part.lstrip())]
        trail = part[len(part.rstrip()):]
        qm = re.match(r"(>+\s*)", s)
        if qm and not tr.startswith(">"):
            tr = qm.group(1) + tr
        out.append(lead + tr.strip() + trail)
    return "".join(out), missing


def validate(src_path, tgt_lang, src_body, tr_body):
    """Solo errori duri: cio' che rende l'atomo impubblicabile. Ritorna una lista.

    Allineata a `verify.py`, che e' il verificatore ufficiale del repo: se questa
    passa e quella boccia, il lavoro andrebbe rifatto a mano. In particolare i
    bersagli si confrontano come lista ORDINATA — perdere un link e' fatale qui,
    mentre in English finiva solo in un rapporto di riparazione.
    """
    problems = []
    sp = verify.prose_blocks(src_body)
    tp = verify.prose_blocks(tr_body)
    if len(sp) != len(tp):
        problems.append("blocchi %d fonte vs %d tradotti" % (len(sp), len(tp)))
    else:
        fab = [(len(a), len(b)) for a, b in zip(sp, tp) if is_fabricated(a, b)]
        if fab:
            problems.append("contenuto FABBRICATO in %d blocchi (es. %d -> %d caratteri)"
                            % (len(fab), fab[0][0], fab[0][1]))
        trunc = [(len(a), len(b)) for a, b in zip(sp, tp) if is_truncated(a, b)]
        if trunc:
            problems.append("contenuto TRONCATO in %d blocchi (es. %d -> %d caratteri)"
                            % (len(trunc), trunc[0][0], trunc[0][1]))

    # Solo i bersagli INVENTATI sono fatali: punterebbero a nodi che non esistono.
    # Un bersaglio perso lascia la pagina pubblicabile, con meno link concettuali:
    # va in coda di riparazione (vedi lost_links), non nel cestino.
    st, tt = link_targets(src_body), link_targets(tr_body)
    invented = sorted(set(tt) - set(st))
    if invented:
        problems.append("wikilink inventati: %s" % invented[:6])

    nolabel = [m.group(1) for m in verify.WIKILINK_RE.finditer(tr_body) if m.group(2) is None]
    if nolabel:
        problems.append("wikilink senza etichetta: %s" % nolabel[:6])

    stray = POISONED_RE.findall(tr_body)
    if stray:
        problems.append("mask token residui: %d (es. %s)" % (len(stray), stray[0]))

    leak = cjk_leak(src_body, tr_body)
    if leak:
        problems.append("caratteri CJK fuggiti: %d (es. %s)" % (len(leak), "".join(leak[:4])))

    if verify.H1_RE.match(src_body.lstrip("\n")) and not verify.H1_RE.match(tr_body.lstrip("\n")):
        problems.append("manca l'H1 che la fonte ha")

    if tr_body.strip() == src_body.strip():
        problems.append("identico alla fonte (non tradotto)")
    elif tgt_lang == "it":
        left = [i for i, b in enumerate(tp) if verify.looks_english(b)]
        if left:
            problems.append("blocchi ancora in inglese: %s" % left[:6])

    return problems


def lost_links(src_body, tr_body):
    """Bersagli presenti nella fonte e assenti dalla traduzione.

    Materiale per la passata di riparazione, non un motivo di scarto. Il conto e'
    sul multiinsieme: se la fonte linka `grace` tre volte e la traduzione due, ne
    manca uno — contarlo come insieme lo nasconderebbe.
    """
    from collections import Counter
    diff = Counter(link_targets(src_body)) - Counter(link_targets(tr_body))
    return sorted(diff.elements())


def write_translation(src_path, tgt_lang, src_fm, tr_body):
    path = sibling_path(src_path, tgt_lang)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(build_fm(src_fm, tgt_lang))
        fh.write(tr_body if tr_body.startswith("\n") else "\n" + tr_body)
    os.replace(tmp, path)                          # atomico: mai un file mezzo scritto
    return path


# --------------------------------------------------------------------------
# enumerazione del corpus
# --------------------------------------------------------------------------
def is_leaf(path):
    """Un atomo da tradurre: `.md` che non e' un sibling di lingua, non e' una copia
    in conflitto di Dropbox e non ha una directory sorella omonima (che ne farebbe
    un aggregato). La regola e' strutturale, non basata sul nome."""
    f = os.path.basename(path)
    if not f.endswith(".md") or SIBLING_RE.search(f):
        return False
    if CONFLICTED_RE.search(f):
        return False
    return not os.path.isdir(path[:-3])


def works_of(author):
    """Opere di un autore: le directory sotto `Atomized/`, in ordine alfabetico."""
    base = os.path.join(PHIL_DIR, author, "Atomized")
    if not os.path.isdir(base):
        return []
    return sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))


def jobs_for_work(author, work):
    """Lavori pendenti di un'opera: `(percorso, lingua)` per ogni traduzione mancante.

    L'ordine mette prima tutte le lingue di uno stesso atomo, cosi' un'opera
    interrotta lascia atomi completi invece che meta' inglesi e meta' italiani.
    """
    base = os.path.join(PHIL_DIR, author, "Atomized", work)
    out = []
    for root, _dirs, files in os.walk(base):
        for f in sorted(files):
            p = os.path.join(root, f)
            if not is_leaf(p):
                continue
            fm, _ = read_atom(p)
            for lang in needed_langs(fm.get("lang", "en")):
                if not os.path.exists(sibling_path(p, lang)):
                    out.append((p, lang))
    return out
