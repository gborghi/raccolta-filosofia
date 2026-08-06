# tests/extract/test_sources.py
import importlib

from scripts.extract.sources import SOURCES, delphi_sources


def test_eight_delphi_sources():
    keys = {s.key for s in delphi_sources()}
    assert keys == {
        "seneca", "pascal", "marx", "hegel",
        "kant", "hume", "locke", "lucretius",
    }


def test_every_source_carries_copyright_metadata():
    for s in SOURCES.values():
        assert s.lang, f"{s.key}: lang mancante"
        assert s.edizione, f"{s.key}: edizione mancante"
        assert s.pd_year is not None, f"{s.key}: pd_year mancante"


def test_every_source_is_public_domain():
    # Nessuna fonte protetta: risolto risalendo agli originali + strip apparati.
    # Se questo test fallisce, il sito sta per pubblicare qualcosa che non può.
    for s in SOURCES.values():
        assert s.pd_year <= 2026, f"{s.key}: pd_year {s.pd_year} — non pubblicabile"


def test_nietzsche_is_german_original_not_translation():
    # regressione: la trad. Newton Compton 2012 era protetta; la Levy inglese
    # è PD solo a metà (Ludovici † 1971 -> 2042). L'originale tedesco no.
    n = SOURCES["nietzsche"]
    assert n.lang == "de"
    assert n.traduttore is None


def test_davila_excluded():
    # unica fonte residua protetta, nessun originale accessibile
    assert "davila" not in SOURCES


def test_raw_root_honours_env_override(monkeypatch):
    # IMPORTANT 7: RAW_ROOT non deve restare saldato a un percorso di una
    # sola macchina -- M1b (cartesio, rousseau, nietzsche, ortega) ne ha
    # bisogno configurabile.
    from scripts.extract import sources as sources_mod
    monkeypatch.setenv("PHILOSOPHY_RAW_ROOT", "/tmp/custom-raw-root")
    importlib.reload(sources_mod)
    try:
        assert sources_mod.RAW_ROOT == "/tmp/custom-raw-root"
    finally:
        # ripristina PRIMA di ricaricare: il reload legge l'env al momento
        # dell'esecuzione, non a quello del teardown del fixture.
        monkeypatch.delenv("PHILOSOPHY_RAW_ROOT", raising=False)
        importlib.reload(sources_mod)


def test_raw_root_default_unchanged_without_env():
    from scripts.extract.sources import RAW_ROOT
    assert RAW_ROOT == r"E:/giovanni/Dropbox/remotedir/libri/notebooklm"
