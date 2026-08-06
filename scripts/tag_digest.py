"""Digest per la passata di tagging: cosa serve per giudicare un'opera.

Titolo + struttura (titoli degli atomi) + un campione di prosa. Deterministico,
nessun LLM qui.
"""
from __future__ import annotations
import re, sys
from pathlib import Path

V = Path(__file__).resolve().parents[2] / "VaultPhilosophy" / "Philosophers"  # fratello di quartz-philosophy/
OUT = Path(__file__).resolve().parents[1] / "data" / "digests"
SAMPLE_WORDS = 700

def fm(text: str, key: str) -> str:
    m = re.search(rf'^{key}:\s*"?(.*?)"?\s*$', text, re.M)
    return m.group(1) if m else ""


# Solo gli atomi base `NNN_slug.md`: le varianti di lingua (`.it.md`, `.en.md`,
# il latino a fronte di Spinoza `.la.md`) sono lo STESSO atomo in un'altra
# lingua — contarle gonfierebbe il conteggio e mescolerebbe latino nel campione
# di prosa che il tagger legge.
def _base_atoms(d: Path) -> list[Path]:
    return [p for p in sorted(d.glob("*.md")) if not re.search(r"\.[a-z]{2}\.md$", p.name)]


def atom_dirs_by_work(ph: Path) -> dict[str, Path]:
    """Opera -> cartella dei suoi atomi, letta dagli atomi stessi.

    NON si ricava il nome della cartella dal nome dell'opera: atomize/run.py lo
    tronca a WORK_DIR_MAX_LEN per il MAX_PATH di Windows (e aggiunge _2, _3 se
    due titoli lunghi troncano uguale). Un `Atomized/<stem intero>` per un'opera
    dal titolo lungo NON ESISTE, e una glob su una cartella inesistente non
    solleva niente: torna una lista vuota. Il digest diceva "atomi: 0" per 41
    opere vere — fra cui testi da 1.700 parole — e chi taggava vedeva un'opera
    senza testo. Alcune sono state taggate cosi', alla cieca, e verify_tags non
    poteva accorgersene: controlla che gli id esistano, non che il tagger abbia
    letto qualcosa.

    Ogni atomo porta nel frontmatter il nome dell'opera da cui viene: quella e'
    la verita', e non va indovinata.
    """
    out: dict[str, Path] = {}
    base = ph / "Atomized"
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        first = next(iter(_base_atoms(d)), None)
        if first is None:
            continue
        w = fm(first.read_text(encoding="utf-8", errors="replace"), "work")
        if w:
            out[w] = d
    return out


def digest(ph: Path) -> str:
    out = []
    dirs = atom_dirs_by_work(ph)
    for raw in sorted((ph / "_raw").glob("*.md")):
        t = raw.read_text(encoding="utf-8", errors="replace")
        body = t.split("---", 2)[-1]
        title = fm(t, "title")
        d = dirs.get(raw.stem)
        atoms = _base_atoms(d) if d else []
        out.append(f"===== OPERA: {raw.stem}")
        out.append(f"titolo: {title}")
        out.append(f"lingua: {fm(t,'lang')} | traduttore: {fm(t,'traduttore')} | tipo: {fm(t,'kind')}")
        out.append(f"parole: {len(body.split()):,} | atomi: {len(atoms)}")
        if atoms:
            # Tutti gli atomi, non i primi 40: la Fisica ne ha 65, e fermarsi a 40
            # nascondeva i libri VII-VIII. Il digest e' l'unica finestra del tagger
            # sull'opera — se tronca in silenzio, chi legge non vede un'opera
            # troncata, vede un'opera che finisce li', e colma il buco a memoria.
            # E' successo davvero: il motore immobile taggato "per notorieta',
            # non visto nel campione".
            names = []
            for a in atoms:
                n = fm(a.read_text(encoding="utf-8", errors="replace"), "atom_title")
                if n and n not in names:
                    names.append(n)
            out.append("struttura: " + _structure(names))
        # Campione di prosa: gli atomi in ordine, fino a SAMPLE_WORDS.
        #
        # Prima si prendeva "il primo atomo oltre 300 parole", e le opere brevi
        # non ne avevano nessuno: un articolo da 151 parole usciva SENZA
        # campione, cioe' senza testo. La soglia nascondeva esattamente i testi
        # che ci starebbero per intero. Un'opera corta va mostrata tutta; una
        # lunga si taglia a SAMPLE_WORDS come sempre.
        ws: list[str] = []
        for a in atoms:
            at = a.read_text(encoding="utf-8", errors="replace").split("---", 2)[-1]
            ws += at.split()
            if len(ws) >= SAMPLE_WORDS:
                break
        if ws:
            out.append("campione: " + " ".join(ws[:SAMPLE_WORDS]))
        else:
            # Nessun atomo: l'opera non e' sul sito. Dirlo, invece di emettere
            # un blocco muto che si legge come "opera senza testo".
            out.append("ATTENZIONE: nessun atomo — opera non atomizzata")
        out.append("")
    return "\n".join(out)

STRUCT_HEAD = 22
STRUCT_TAIL = 5


def _structure(names: list[str]) -> str:
    """La struttura dell'opera, e se e' troncata lo dice.

    Un elenco troppo lungo va tagliato, ma il taglio deve essere VISIBILE: si
    mostrano la testa e la coda, cosi' chi legge sa dove finisce l'opera davvero
    e non deve indovinarlo. Il buco dichiarato e' la parte utile.
    """
    if len(names) <= STRUCT_HEAD + STRUCT_TAIL:
        return " | ".join(names)
    hidden = len(names) - STRUCT_HEAD - STRUCT_TAIL
    return (
        " | ".join(names[:STRUCT_HEAD])
        + f" | […{hidden} non mostrati…] | "
        + " | ".join(names[-STRUCT_TAIL:])
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for ph in sorted(V.iterdir()):
        if not (ph / "_raw").is_dir(): continue
        p = OUT / f"{ph.name}.md"
        p.write_text(digest(ph), encoding="utf-8")
        n = p.read_text(encoding="utf-8").count("===== OPERA:")
        print(f"{ph.name:10} {n:2} opere  {p.stat().st_size//1024:4}KB")
    return 0

if __name__ == "__main__":
    sys.exit(main())
