"""Atomizzazione bilingue per Spinoza: le opere con originale latino a fronte
diventano atomi INGLESI (`NNN_slug.md`) affiancati dai gemelli LATINI
(`NNN_slug.la.md`), come le traduzioni `.it.md`/`.en.md` del progetto — cosi'
il sito puo' commutare lingua col solito bottone.

L'allineamento e' STRUTTURALE, non a conteggio di parole: inglese e latino si
tagliano sugli stessi ancoraggi (proposizioni per l'Etica, capitoli per i due
Trattati), un'unita' = un atomo, appaiati per indice. Il numero di ancoraggi
DEVE combaciare fra le due lingue (verificato: Etica 264=264, TTP 21=21,
TP 12=12); se non combacia ci si ferma — un allineamento sbagliato e' peggio
di nessun latino.

L'Emendatio ha latino nell'edizione ma NON e' allineabile (l'inglese Elwes non
porta la numerazione dei paragrafi che il latino ha): resta solo-inglese, come
il Breve Trattato e le Lettere (che il latino non ce l'hanno affatto). Quelle
tre opere le atomizza la pipeline standard (scripts/atomize/run.py).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from scripts.extract.common import slugify
from scripts.extract.spinoza import extract as spinoza_extract
from scripts.extract.spinoza import find_epub
from scripts.extract.sources import SOURCES

from .run import (
    ATOM_SLUG_MAX_LEN,
    _atom_frontmatter,
    _check_path_len,
    _parse_frontmatter,
    _resolve_dir_name,
    _strip_title_heading,
)

VAULT_ROOT = Path(__file__).resolve().parents[3] / "VaultPhilosophy"  # fratello di quartz-philosophy/

# Opera -> (ancoraggio inglese, ancoraggio latino). Un ancoraggio e' una riga
# (paragrafo, dopo il de-wrap) che apre un'unita' strutturale.
ANCHORS = {
    "Ethics": (
        re.compile(r"^(PART\b|PROP\.)"),
        re.compile(r"^(PARS\b|PROPOSITIO\b)"),
    ),
    "Theological-Political Treatise": (
        re.compile(r"^(PREFACE\b|CHAPTER\b)"),
        re.compile(r"^(Praefatio\b|Caput\b)"),
    ),
    "Political Treatise": (
        re.compile(r"^(Preface\b|Chapter\b)"),
        re.compile(r"^(TRACTATUS\b|CAPUT\b)"),
    ),
}


def _split_anchored(text: str, anchor: re.Pattern) -> list[tuple[str, str]]:
    """(titolo unita', corpo) per ogni unita'. Il testo prima del primo
    ancoraggio (se c'e') si fonde nella prima unita', cosi' il numero di unita'
    e' esattamente il numero di ancoraggi in entrambe le lingue."""
    lines = text.split("\n")
    idxs = [i for i, l in enumerate(lines) if anchor.match(l.strip())]
    if not idxs:
        return []
    segs: list[tuple[str, str]] = []
    for j, i in enumerate(idxs):
        stop = idxs[j + 1] if j + 1 < len(idxs) else len(lines)
        title = lines[i].strip()
        body = "\n".join(lines[i + 1:stop]).strip()
        segs.append((title, body))
    if idxs[0] > 0:
        pre = "\n".join(lines[:idxs[0]]).strip()
        if pre:
            t0, b0 = segs[0]
            segs[0] = (t0, f"{pre}\n\n{b0}" if b0 else pre)
    return segs


def _write_atom(path: Path, fm: str, title: str, body: str) -> None:
    _check_path_len(path)
    path.write_text(f"{fm}\n\n# {title}\n\n{body.strip()}\n", encoding="utf-8")


def atomize_bilingual(vault_root: Path = VAULT_ROOT) -> int:
    src = SOURCES["spinoza"]
    latin = {w.title: w.la_text for w in spinoza_extract(find_epub(src)).works if w.la_text}
    raw_dir = vault_root / "Philosophers" / "Spinoza" / "_raw"
    atomized = vault_root / "Philosophers" / "Spinoza" / "Atomized"

    total = 0
    for title, (en_anchor, la_anchor) in ANCHORS.items():
        raw_path = raw_dir / f"{slugify(title)}.md"
        fields, body = _parse_frontmatter(raw_path.read_text(encoding="utf-8"))
        en_body = _strip_title_heading(body)
        la_text = latin[title]

        en_segs = _split_anchored(en_body, en_anchor)
        la_segs = _split_anchored(la_text, la_anchor)
        if len(en_segs) != len(la_segs):
            raise SystemExit(
                f"ALLINEAMENTO FALLITO {title!r}: {len(en_segs)} unita' EN vs "
                f"{len(la_segs)} LA — non scrivo nulla"
            )

        work = raw_path.stem
        out_dir = atomized / _resolve_dir_name(work, atomized)
        out_dir.mkdir(parents=True, exist_ok=True)
        la_fields = dict(fields, lang="la")

        for n, ((en_t, en_b), (la_t, la_b)) in enumerate(zip(en_segs, la_segs), 1):
            # L'identita' dell'atomo (atom_n, atom_title inglese) e' condivisa:
            # e' cio' che appaia il gemello latino al suo originale inglese.
            slug = slugify(en_t)[:ATOM_SLUG_MAX_LEN].rstrip("_") or f"unit_{n}"
            base = out_dir / f"{n:03d}_{slug}"
            _write_atom(base.with_suffix(".md"),
                        _atom_frontmatter(fields, work, n, en_t), en_t, en_b)
            _write_atom(Path(f"{base}.la.md"),
                        _atom_frontmatter(la_fields, work, n, en_t), la_t, la_b)
        total += len(en_segs)
        print(f"  {title:45} {len(en_segs):4} atomi EN+LA")

    print(f"Spinoza bilingue: {total} coppie di atomi (.md + .la.md)")
    return 0


if __name__ == "__main__":
    sys.exit(atomize_bilingual())
