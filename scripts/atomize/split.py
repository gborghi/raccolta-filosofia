# scripts/atomize/split.py
from __future__ import annotations

import re
from dataclasses import dataclass

from .headings import heading_lines

TARGET = 1500
MAX_WORDS = 2600
MIN_WORDS = 250

# Un paragrafo non si taglia mai a meta': e' l'unita' che l'autore ha scritto.
# Ma un "paragrafo" piu' lungo di MAX_WORDS non e' un paragrafo — e' una fonte
# che non ha segnato i confini. Succede coi PDF, dove le righe estratte sono
# righe di stampa e non c'e' nessuna riga vuota: la Summa di Tommaso arrivava
# qui come 2 paragrafi da 113.314 parole, e ne usciva un atomo unico da 1,5 MB
# che avrebbe affondato il lettore SPA.
#
# Quindi si taglia lo stesso, ma a fine frase, che e' il confine meno peggio
# quando quello vero manca. Gli atomi restano brutti — ed e' giusto che si veda:
# il difetto e' della fonte, e va corretto la', non nascosto qui.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Atom:
    title: str
    text: str
    n: int


def _paragraphs(lines: list[str]) -> list[str]:
    paras: list[str] = []
    cur: list[str] = []
    for l in lines:
        if l.strip():
            cur.append(l)
        elif cur:
            paras.append("\n".join(cur))
            cur = []
    if cur:
        paras.append("\n".join(cur))
    return paras


def _split_runaway(p: str) -> list[str]:
    """Un blocco oltre MAX_WORDS, tagliato a fine frase.

    Rete di sicurezza per le fonti che non segnano i paragrafi (vedi
    SENTENCE_END). Ritorna [p] intatto se il blocco e' di misura normale, cosi'
    il caso sano non paga nulla.
    """
    if len(p.split()) <= MAX_WORDS:
        return [p]
    out: list[str] = []
    buf: list[str] = []
    n = 0
    for s in SENTENCE_END.split(p):
        w = len(s.split())
        if n and n + w > TARGET:
            out.append(" ".join(buf))
            buf, n = [s], w
        else:
            buf.append(s)
            n += w
    if buf:
        out.append(" ".join(buf))
    return out


def _chunk(lines: list[str], title: str, out: list[tuple[str, str]]) -> None:
    """Spezza a confini di paragrafo. Un paragrafo non si taglia mai a meta'."""
    buf: list[str] = []
    n = 0
    for para in _paragraphs(lines):
        for p in _split_runaway(para):
            w = len(p.split())
            if n and n + w > TARGET:
                out.append((title, "\n\n".join(buf)))
                buf, n = [p], w
            else:
                buf.append(p)
                n += w
    if buf:
        out.append((title, "\n\n".join(buf)))


def split_work(body: str) -> list[Atom]:
    lines = body.split("\n")
    heads, end = heading_lines(lines)
    ks = sorted(heads)
    out: list[tuple[str, str]] = []

    if not ks:
        _chunk(lines[end + 1:], "(intero)", out)
    else:
        if ks[0] > end + 1:
            _chunk(lines[end + 1: ks[0]], "(apertura)", out)
        for j, i in enumerate(ks):
            stop = ks[j + 1] if j + 1 < len(ks) else len(lines)
            _chunk(lines[i + 1: stop], heads[i], out)

    return [Atom(title=t, text=x, n=k + 1)
            for k, (t, x) in enumerate((t, x) for t, x in out if x.strip())]
