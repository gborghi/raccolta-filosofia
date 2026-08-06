# scripts/atomize/run.py
"""Emissione: dai file _raw agli atomi in Atomized/.

Il frontmatter dell'atomo eredita i campi dell'opera (li scrive render() in
scripts/extract/common.py) e aggiunge work, atom_n, atom_title, kind: atom.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.extract.common import slugify

from .split import split_work

VAULT_ROOT = Path(__file__).resolve().parents[3] / "VaultPhilosophy"  # fratello di quartz-philosophy/

# Campi ereditati dall'opera: solo questi, non title/anno_edizione/kind.
INHERITED_KEYS = ("philosopher", "lang", "edizione", "traduttore", "pd_year", "source_key")

# Windows MAX_PATH (260) morde su titoli lunghi (es. intestazioni Hegel di
# 100+ caratteri) sommati a percorsi Dropbox gia' lunghi di loro. atom_n e'
# gia' unico nella cartella: lo slug puo' essere accorciato senza perdere
# unicita'. Il titolo completo resta comunque in atom_title/work nel
# frontmatter: qui si accorcia solo il nome file.
WORK_DIR_MAX_LEN = 60
ATOM_SLUG_MAX_LEN = 40
MAX_PATH_LEN = 260


@dataclass
class WorkReport:
    philosopher: str
    work: str
    atoms: int


def _yaml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Frontmatter semplice prodotto da render() in common.py: `key: "value"`
    o `key: value` (numeri, null). Ritorna (campi senza virgolette, corpo dopo
    il secondo `---`)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    fields: dict[str, str] = {}
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        line = lines[i]
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value.startswith('"') and value.endswith('"') and len(value) >= 2:
                value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            fields[key] = value
        i += 1
    body = "\n".join(lines[i + 1:])
    return fields, body


def _strip_title_heading(body: str) -> str:
    """Il corpo comincia con `# TITLE` (scritto da render()): lo si toglie,
    il testo dell'opera comincia dopo."""
    lines = body.split("\n")
    j = 0
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j < len(lines) and lines[j].lstrip().startswith("#"):
        j += 1
    return "\n".join(lines[j:])


def _atom_frontmatter(fields: dict[str, str], work: str, atom_n: int, atom_title: str) -> str:
    lines = ["---"]
    for key in INHERITED_KEYS:
        value = fields.get(key)
        if value is None or value == "null":
            lines.append(f"{key}: null")
        elif key == "pd_year":
            lines.append(f"pd_year: {value}")
        else:
            lines.append(f'{key}: "{_yaml_escape(value)}"')
    lines.append(f'work: "{_yaml_escape(work)}"')
    lines.append(f"atom_n: {atom_n}")
    lines.append(f'atom_title: "{_yaml_escape(atom_title)}"')
    lines.append('kind: "atom"')
    lines.append("---")
    return "\n".join(lines)


def _resolve_dir_name(work: str, parent: Path) -> str:
    """Nome cartella accorciato a WORK_DIR_MAX_LEN, disambiguato in modo
    deterministico (_2, _3, ...) se due opere diverse troncano allo stesso
    nome. L'ordine e' quello di elaborazione (discover_raw_files e' ordinato),
    quindi la disambiguazione e' riproducibile run dopo run."""
    base = work[:WORK_DIR_MAX_LEN].rstrip("_")
    if not (parent / base).exists():
        return base
    n = 2
    while (parent / f"{base}_{n}").exists():
        n += 1
    return f"{base}_{n}"


def _check_path_len(path: Path) -> None:
    resolved = str(path.resolve())
    if len(resolved) >= MAX_PATH_LEN:
        raise RuntimeError(
            f"path >= {MAX_PATH_LEN} chars (Windows MAX_PATH), "
            f"would be unreadable: {resolved} ({len(resolved)} chars)"
        )


def atomize_work(path: Path, out_root: Path) -> WorkReport:
    text = path.read_text(encoding="utf-8")
    fields, body = _parse_frontmatter(text)
    body = _strip_title_heading(body)
    atoms = split_work(body)

    philosopher = fields.get("philosopher", "")
    work = path.stem
    phil_atomized_dir = Path(out_root) / "Philosophers" / philosopher / "Atomized"
    dir_name = _resolve_dir_name(work, phil_atomized_dir)
    out_dir = phil_atomized_dir / dir_name
    _check_path_len(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for atom in atoms:
        fm = _atom_frontmatter(fields, work, atom.n, atom.title)
        content = f"{fm}\n\n# {atom.title}\n\n{atom.text.strip()}\n"
        slug = slugify(atom.title)[:ATOM_SLUG_MAX_LEN].rstrip("_")
        atom_path = out_dir / f"{atom.n:03d}_{slug}.md"
        _check_path_len(atom_path)
        atom_path.write_text(content, encoding="utf-8")

    return WorkReport(philosopher=philosopher, work=work, atoms=len(atoms))


def discover_raw_files(vault_root: Path) -> list[Path]:
    return sorted((Path(vault_root) / "Philosophers").glob("*/_raw/*.md"))


def main(vault_root: Path = VAULT_ROOT) -> int:
    raw_files = discover_raw_files(vault_root)
    reports = [atomize_work(p, out_root=vault_root) for p in raw_files]
    total_atoms = sum(r.atoms for r in reports)
    print(f"{len(reports)} opere -> {total_atoms} atomi")
    for r in reports:
        print(f"  {r.philosopher:20} {r.work:50} {r.atoms:4} atomi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
