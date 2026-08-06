from __future__ import annotations

import glob
import re
from dataclasses import dataclass
from pathlib import Path

from .sources import RAW_ROOT, Source


@dataclass
class Work:
    title: str
    text: str
    kind: str = "work"          # "work" | "latin"
    traduttore: str | None = None
    tomo: str | None = None     # provenienza in edizioni multi-tomo (es. Ortega)


def slugify(s: str) -> str:
    # Il corpo Delphi aggiunge il titolo originale dopo un em-dash: tagliarlo.
    s = re.split(r"\s+[—–]\s+", s)[0]
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return re.sub(r"\s+", "_", s.strip())


def _yaml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def render(work: Work, source: Source) -> str:
    traduttore = work.traduttore or source.traduttore
    lines = [
        "---",
        f'title: "{_yaml_escape(work.title)}"',
        f'philosopher: "{_yaml_escape(source.name)}"',
        f'lang: "{_yaml_escape(source.lang)}"',
        f'edizione: "{_yaml_escape(source.edizione)}"',
        f'traduttore: "{_yaml_escape(traduttore)}"' if traduttore else "traduttore: null",
        f"anno_edizione: {source.anno_edizione}" if source.anno_edizione else "anno_edizione: null",
        f"pd_year: {source.pd_year}",
        f'source_key: "{_yaml_escape(source.key)}"',
        f'kind: "{_yaml_escape(work.kind)}"',
        f'tomo: "{_yaml_escape(work.tomo)}"' if work.tomo else "tomo: null",
        "---",
        "",
        f"# {work.title}",
        "",
        work.text.strip(),
        "",
    ]
    return "\n".join(lines)


def write_work(work: Work, source: Source, vault_root: Path) -> Path:
    out_dir = Path(vault_root) / "Philosophers" / source.name / "_raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slugify(work.title)}.md"
    path.write_text(render(work, source), encoding="utf-8")
    return path


_GROUPTXT_MARKER_RE = re.compile(
    r"^===== (?:INIZIO|FINE) FILE:.*=====[ \t]*\n?", re.MULTILINE
)


def _strip_grouptxt_markers(text: str) -> str:
    """Rimuove i marker di grouptxt.sh (===== INIZIO/FINE FILE: ... =====)
    che leakano in mezzo ai blob concatenati. Non sono contenuto."""
    return _GROUPTXT_MARKER_RE.sub("", text)


def load_raw(source: Source) -> str:
    """Concatena i blob della fonte. Generico: non è specifico a Delphi."""
    pattern = str(Path(RAW_ROOT) / source.key / source.glob)
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"nessun file per {source.key}: {pattern}")
    return _strip_grouptxt_markers(
        "\n".join(
            Path(p).read_text(encoding="utf-8", errors="replace") for p in paths
        )
    )
