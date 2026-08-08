# -*- coding: utf-8 -*-
"""Traduce le foglie pendenti di UN autore con HY, opera per opera.

    python3 run_author_hy.py Augustine
    HY_WORKERS=4 python3 run_author_hy.py Rousseau --limit 20

Il ciclo e' **per opera, non per lingua**: di ogni opera si producono tutte le
traduzioni mancanti — italiano *e* inglese — prima di passare alla successiva, e
a opera chiusa parte una mail con lo stato e le due stime (fine dell'autore, fine
del repo). Un'opera gia' completa non manda nulla: 1180 mail di "niente da fare"
sarebbero rumore.

Riprendibile: un atomo che ha gia' il suo sibling non viene mai riconsiderato,
quindi il runner si puo' uccidere e rilanciare senza perdere lavoro.
"""
import argparse
import datetime
import json
import os
import queue
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hy_tower as T  # noqa: E402

LOG_DIR = T.LOG_DIR
PROGRESS_PATH = os.path.join(LOG_DIR, "progress.json")
REJECTED_PATH = os.path.join(LOG_DIR, "rejected.jsonl")
CACHE_PATH = os.path.join(T.ROOT, "data", "hy_translate_cache.jsonl")
# Coda di riparazione dei link: un bersaglio che il modello non ha ricollocato non
# fa scartare l'atomo (la pagina si pubblica lo stesso, con meno link), ma va
# registrato o l'arretrato diventa invisibile — in English e' cosi' che 40.320
# link persi non si sono mai auto-segnalati.
LINKFIX_PATH = os.path.join(T.ROOT, "data", "hy_linkfix.jsonl")
DEFAULT_TO = os.environ.get("TRANSLATE_MAIL_TO", "gio.borghi@gmail.com")

_print_lock = threading.Lock()
_rej_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


# --------------------------------------------------------------------------
# stato e stime
# --------------------------------------------------------------------------
def load_progress():
    if os.path.exists(PROGRESS_PATH):
        try:
            with open(PROGRESS_PATH, encoding="utf-8") as fh:
                return json.load(fh)
        except ValueError:
            pass
    return {"units": 0, "seconds": 0.0}


def save_progress(p):
    os.makedirs(LOG_DIR, exist_ok=True)
    tmp = PROGRESS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(p, fh, indent=2)
    os.replace(tmp, PROGRESS_PATH)


def census():
    """Unita' ancora da produrre, per autore. Una passata sola, all'avvio.

    Rifarla a ogni opera costerebbe una camminata su 26.000 file per 1.180 volte:
    si conta una volta e poi si scala in memoria.
    """
    out = {}
    for author in sorted(os.listdir(T.PHIL_DIR)):
        base = os.path.join(T.PHIL_DIR, author, "Atomized")
        if not os.path.isdir(base):
            continue
        n = 0
        for root, _dirs, files in os.walk(base):
            for f in files:
                p = os.path.join(root, f)
                if not T.is_leaf(p):
                    continue
                fm, _ = T.read_atom(p)
                for lang in T.needed_langs(fm.get("lang", "en")):
                    if not os.path.exists(T.sibling_path(p, lang)):
                        n += 1
        out[author] = n
    return out


def fmt_dur(seconds):
    if seconds <= 0 or seconds != seconds:      # <=0 o NaN
        return "n/d"
    seconds = int(seconds)
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return "%dg %02dh %02dm" % (d, h, m)
    return "%dh %02dm" % (h, m)


def fmt_eta(seconds):
    if seconds <= 0:
        return "n/d"
    when = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    return when.strftime("%a %d/%m alle %H:%M")


# --------------------------------------------------------------------------
# esecuzione di un'opera
# --------------------------------------------------------------------------
def record_reject(path, lang, problems):
    os.makedirs(LOG_DIR, exist_ok=True)
    row = {"atom": os.path.relpath(path, T.VAULT_ROOT), "lang": lang,
           "problems": problems, "when": datetime.datetime.now().isoformat(timespec="seconds")}
    with _rej_lock:
        with open(REJECTED_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def record_linkfix(path, lang, lost):
    row = {"atom": os.path.relpath(path, T.VAULT_ROOT), "lang": lang, "lost": lost}
    with _rej_lock:
        with open(LINKFIX_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_jobs(jobs, cache, workers):
    """Esegue i lavori su N thread. Ritorna (ok, rifiutati, falliti, per_lingua, link_persi)."""
    q = queue.Queue()
    for j in jobs:
        q.put(j)
    counters = {"ok": 0, "reject": 0, "fail": 0, "lost": 0}
    per_lang = {}
    clock = {"done": 0}
    total = len(jobs)

    def worker():
        while True:
            try:
                path, lang = q.get_nowait()
            except queue.Empty:
                return
            try:
                src_fm, src_body = T.read_atom(path)
                tr_body, missing = T.translate_atom(path, lang, cache)
                problems = T.validate(path, lang, src_body, tr_body)
                if problems:
                    counters["reject"] += 1
                    record_reject(path, lang, problems)
                    log("   REJECT %s [%s]: %s"
                        % (os.path.basename(path), lang, "; ".join(problems)[:180]))
                else:
                    T.write_translation(path, lang, src_fm, tr_body)
                    counters["ok"] += 1
                    per_lang[lang] = per_lang.get(lang, 0) + 1
                    lost = T.lost_links(src_body, tr_body)
                    if lost:
                        counters["lost"] += len(lost)
                        record_linkfix(path, lang, lost)
            except Exception as e:
                counters["fail"] += 1
                record_reject(path, lang, ["eccezione: %s" % e])
                log("   FAIL   %s [%s]: %s" % (os.path.basename(path), lang, e))
            finally:
                clock["done"] += 1
                if clock["done"] % 25 == 0:
                    log("   ... %d/%d unita'" % (clock["done"], total))
                q.task_done()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return counters["ok"], counters["reject"], counters["fail"], per_lang, counters["lost"]


# --------------------------------------------------------------------------
# mail
# --------------------------------------------------------------------------
def send_mail(to, subject, body):
    script = os.path.join(HERE, "notify_gas_mail.py")
    try:
        r = subprocess.run([sys.executable, script, "--to", to, "--subject", subject],
                           input=body.encode("utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        if r.returncode:
            log("   mail NON inviata: %s" % r.stderr.decode("utf-8", "replace").strip()[:300])
            return False
        return True
    except Exception as e:
        log("   mail NON inviata: %s" % e)
        return False


def work_report(author, work, res, elapsed, rate, done_author, tot_author,
                done_repo, tot_repo, next_work):
    ok, rej, fail, per_lang, lost = res
    left_a = max(0, tot_author - done_author)
    left_r = max(0, tot_repo - done_repo)
    eta_a = left_a / rate if rate > 0 else 0
    eta_r = left_r / rate if rate > 0 else 0
    langs = ", ".join("%s %d" % (k.upper(), v) for k, v in sorted(per_lang.items())) or "nessuna"
    pct_a = 100.0 * done_author / tot_author if tot_author else 100.0
    pct_r = 100.0 * done_repo / tot_repo if tot_repo else 100.0
    return "\n".join([
        "Opera completata: %s" % work,
        "Autore: %s" % author,
        "",
        "  unita' prodotte  : %d  (%s)" % (ok, langs),
        "  rifiutate        : %d" % rej,
        "  fallite          : %d" % fail,
        "  link da riagganciare : %d  (data/hy_linkfix.jsonl)" % lost,
        "  tempo dell'opera : %s" % fmt_dur(elapsed),
        "  ritmo medio      : %.1f unita'/ora" % (rate * 3600.0),
        "",
        "Autore %s" % author,
        "  fatte   : %d / %d unita' (%.1f%%)" % (done_author, tot_author, pct_a),
        "  restano : %d unita'" % left_a,
        "  stima   : %s  ->  %s" % (fmt_dur(eta_a), fmt_eta(eta_a)),
        "",
        "Intero repo",
        # `done_repo` conta le unita' prodotte da questa coda, non dall'inizio dei
        # tempi: `tot_repo` e' l'arretrato misurato all'avvio, quindi i due numeri
        # sono coerenti fra loro ma si azzerano a ogni rilancio.
        "  prodotte in questa coda : %d / %d (%.1f%%)" % (done_repo, tot_repo, pct_r),
        "  restano : %d unita'" % left_r,
        "  stima   : %s  ->  %s" % (fmt_dur(eta_r), fmt_eta(eta_r)),
        "",
        "Prossima opera: %s" % (next_work or "— autore concluso —"),
        "",
        "(le stime usano il ritmo cumulato di tutte le sessioni; i rifiuti restano",
        " senza traduzione e vengono ripescati da soli al prossimo giro sull'autore)",
    ])


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("author")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("HY_WORKERS", "4")))
    ap.add_argument("--limit", type=int, default=None, help="max unita' in totale (prova)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-mail", action="store_true")
    ap.add_argument("--to", default=DEFAULT_TO)
    a = ap.parse_args()

    author = a.author
    if not os.path.isdir(os.path.join(T.PHIL_DIR, author)):
        print("autore inesistente: %s" % author)
        return 1

    works = T.works_of(author)
    log("### %s: %d opere, %d worker, modello %s"
        % (author, len(works), a.workers, T.MODEL))

    if a.dry_run:
        tot = 0
        for w in works:
            jobs = T.jobs_for_work(author, w)
            tot += len(jobs)
            if jobs:
                langs = {}
                for _p, l in jobs:
                    langs[l] = langs.get(l, 0) + 1
                log("  %-60s %4d  %s" % (w[:60], len(jobs), langs))
        log("TOTALE pendenti per %s: %d unita'" % (author, tot))
        return 0

    log("censimento del repo in corso...")
    per_author = census()
    tot_repo = sum(per_author.values())
    tot_author = per_author.get(author, 0)
    log("pendenti: %d per %s, %d nel repo" % (tot_author, author, tot_repo))
    if not tot_author:
        log("niente da fare per %s" % author)
        return 0

    cache = T.Cache(CACHE_PATH)
    log("cache calda con %d blocchi" % len(cache.d))

    prog = load_progress()
    done_author = 0
    done_repo = tot_repo - sum(per_author.values())   # 0 all'avvio, cresce sotto
    budget = a.limit

    for idx, work in enumerate(works):
        jobs = T.jobs_for_work(author, work)
        if not jobs:
            continue
        # `--limit` serve alle prove: taglia la lista a meta' opera, e in quel caso
        # l'opera NON e' completa. La mail dice "completata", quindi non va mandata.
        partial = False
        if budget is not None:
            if budget <= 0:
                log("limite raggiunto, mi fermo")
                break
            partial = len(jobs) > budget
            jobs = jobs[:budget]
        log("[%d/%d] %s -> %d unita'" % (idx + 1, len(works), work, len(jobs)))
        t0 = time.time()
        res = run_jobs(jobs, cache, a.workers)
        elapsed = time.time() - t0
        ok = res[0]
        if budget is not None:
            budget -= len(jobs)

        # Il ritmo si cumula fra le sessioni: una sola opera e' un campione troppo
        # piccolo per una stima a settimane.
        prog["units"] = prog.get("units", 0) + ok
        prog["seconds"] = prog.get("seconds", 0.0) + elapsed
        rate = (prog["units"] / prog["seconds"]) if prog["seconds"] > 0 else 0.0
        prog["rate_units_per_hour"] = rate * 3600.0
        prog["last"] = {"author": author, "work": work,
                        "when": datetime.datetime.now().isoformat(timespec="seconds")}
        save_progress(prog)

        done_author += ok
        done_repo += ok
        nxt = None
        for w2 in works[idx + 1:]:
            if T.jobs_for_work(author, w2):
                nxt = w2
                break

        log("      ok %d, reject %d, fail %d, link persi %d in %s (%.1f u/h)"
            % (res[0], res[1], res[2], res[4], fmt_dur(elapsed), rate * 3600.0))

        if partial:
            log("      (opera troncata da --limit: nessuna mail)")
        elif not a.no_mail:
            body = work_report(author, work, res, elapsed, rate,
                               done_author, tot_author, done_repo, tot_repo, nxt)
            send_mail(a.to, "[filosofia] %s - %s completata" % (author, work[:60]), body)

    log("### %s: chiuso. %d unita' in questa sessione" % (author, done_author))
    return 0


if __name__ == "__main__":
    sys.exit(main())
