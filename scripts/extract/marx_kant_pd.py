# scripts/extract/marx_kant_pd.py
"""Orchestrazione delle sostituzioni PD di Marx e Kant elencate nella
commessa (7 opere: 2 restano in inglese con traduttore diverso, 5 passano
all'originale tedesco), piu' l'estensione decisa per Das Kapital II/III
(vedi docstring marx_de.py). Stesso pattern di aristotle_pd.py: chiamato DOPO
gli adapter Delphi in run.py, cosi' sovrascrive i _raw gia' scritti; usa un
render locale (non common.write_work) perche' ogni opera ha edizione/
traduttore/pd_year propri, non quelli fissi del Source Delphi condiviso.

Le opere che CAMBIANO titolo (le 5 tedesche) devono anche cancellare il
_raw inglese superato: common.slugify(titolo) cambia, quindi write_work
scriverebbe un file NUOVO lasciando il vecchio protetto ancora nel vault
("stesso posto, il vecchio sparisce" — richiesta esplicita della commessa).
CAPITAL e MARXS_INAUGURAL_ADDRESS non cambiano titolo: si sovrascrivono da
soli, nessuna cancellazione necessaria.
"""
from __future__ import annotations

from pathlib import Path

from . import capital_en, kant_de, marx_de, marx_inaugural_en
from .common import slugify

VAULT_ROOT = Path(__file__).resolve().parents[3] / "VaultPhilosophy"  # fratello di quartz-philosophy/
MARX_DIR = VAULT_ROOT / "Philosophers" / "Marx" / "_raw"
KANT_DIR = VAULT_ROOT / "Philosophers" / "Kant" / "_raw"

_KANT_DEATH_PD_YEAR = 1875   # Kant † 1804, nessun traduttore -> 1804 + 71
_MARX_DEATH_PD_YEAR = 1954   # Marx † 1883, nessun traduttore -> 1883 + 71
_MOORE_AVELING_PD_YEAR = 1982  # Moore † 1911 (l'ultimo dei due a morire) + 71


def _yaml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _render(*, title: str, philosopher: str, lang: str, edizione: str,
            traduttore: str | None, anno_edizione: int | None, pd_year: int,
            kind: str, text: str) -> str:
    lines = [
        "---",
        f'title: "{_yaml_escape(title)}"',
        f'philosopher: "{_yaml_escape(philosopher)}"',
        f'lang: "{_yaml_escape(lang)}"',
        f'edizione: "{_yaml_escape(edizione)}"',
        f'traduttore: "{_yaml_escape(traduttore)}"' if traduttore else "traduttore: null",
        f"anno_edizione: {anno_edizione}" if anno_edizione else "anno_edizione: null",
        f"pd_year: {pd_year}",
        f'source_key: "{philosopher.lower()}"',
        f'kind: "{_yaml_escape(kind)}"',
        "tomo: null",
        "---",
        "",
        f"# {title}",
        "",
        text.strip(),
        "",
    ]
    return "\n".join(lines)


def _write(*, out_dir: Path, title: str, **kwargs) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slugify(title)}.md"
    path.write_text(_render(title=title, **kwargs), encoding="utf-8")
    return path


def _delete(out_dir: Path, filename: str) -> Path:
    path = out_dir / filename
    path.unlink(missing_ok=True)
    return path


def run_marx_kant_pd() -> list[str]:
    log: list[str] = []

    # ------------------------------------------------------------------
    # Restano in inglese, traduttore sostituito (2 opere della commessa)
    # ------------------------------------------------------------------
    capital_result = capital_en.extract(capital_en.find_epub())
    for w in capital_result.works:
        path = _write(
            out_dir=MARX_DIR, title=w.title, philosopher="Marx", lang="en",
            edizione="Marxists Internet Archive, First English edition 1887 "
                     "(tr. Samuel Moore & Edward Aveling, ed. Friedrich Engels) "
                     "— Volume I soltanto: Volumi II e III sostituiti in tedesco, vedi sotto",
            traduttore=w.traduttore, anno_edizione=1887, pd_year=_MOORE_AVELING_PD_YEAR,
            kind=w.kind, text=w.text,
        )
        log.append(f"sostituita: CAPITAL (Vol. I) -> Moore & Aveling 1887, PD ({path})")

    inaugural_result = marx_inaugural_en.extract(marx_inaugural_en.find_html())
    for w in inaugural_result.works:
        path = _write(
            out_dir=MARX_DIR, title=w.title, philosopher="Marx", lang="en",
            edizione="Marxists Internet Archive (pamphlet originale 1864, Londra)",
            traduttore=w.traduttore, anno_edizione=1864, pd_year=_MARX_DEATH_PD_YEAR,
            kind=w.kind, text=w.text,
        )
        log.append(
            f"sostituita: MARX'S INAUGURAL ADDRESS -> nessun traduttore "
            f"(Marx scrisse in inglese), traduttore=null ({path})"
        )

    # ------------------------------------------------------------------
    # Passano al tedesco, nessuna alternativa PD in inglese (5 opere della
    # commessa + estensione Kapital II/III, vedi marx_de.py)
    # ------------------------------------------------------------------
    kant_result = kant_de.extract(kant_de.find_epub())
    for w in kant_result.works:
        path = _write(
            out_dir=KANT_DIR, title=w.title, philosopher="Kant", lang="de",
            edizione="e-artnow, \"Sämtliche Werke\" (2016) — originale tedesco",
            traduttore=None, anno_edizione=2016, pd_year=_KANT_DEATH_PD_YEAR,
            kind=w.kind, text=w.text,
        )
        log.append(f"sostituita: {w.title} -> tedesco originale, e-artnow 2016 ({path})")

    for old in (
        "AN_ANSWER_TO_THE_QUESTION_WHAT_IS_ENLIGHTENMENT.md",
        "UNIVERSAL_NATURAL_HISTORY_AND_THEORY_OF_HEAVEN.md",
    ):
        path = _delete(KANT_DIR, old)
        log.append(f"cancellato (sostituito da originale tedesco, titolo cambiato): {path}")

    marx_result = marx_de.extract(marx_de.find_epub())
    for w in marx_result.works:
        path = _write(
            out_dir=MARX_DIR, title=w.title, philosopher="Marx", lang="de",
            edizione="andhof, \"Gesammelte Werke – Gesamtausgabe\" (2015) — originale tedesco",
            traduttore=None, anno_edizione=2015, pd_year=_MARX_DEATH_PD_YEAR,
            kind=w.kind, text=w.text,
        )
        log.append(f"sostituita: {w.title} -> tedesco originale, andhof 2015 ({path})")

    for old in (
        "CRITIQUE_OF_HEGELS_PHILOSOPHY_OF_RIGHT_1843.md",
        "ON_THE_JEWISH_QUESTION_1843.md",
        "A_CONTRIBUTION_TO_THE_CRITIQUE_OF_POLITICAL_ECONOMY_1859.md",
    ):
        path = _delete(MARX_DIR, old)
        log.append(f"cancellato (sostituito da originale tedesco, titolo cambiato): {path}")

    return log
