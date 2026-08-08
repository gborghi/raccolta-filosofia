#!/usr/bin/env python3
"""Manda una mail attraverso l'Apps Script Execution API di `wiligelmo-gas`.

Serve perche' il runner delle traduzioni gira **staccato dalla sessione**: i tool
MCP vivono dentro Claude Code e un processo in background non puo' chiamarli.
Qui si rifa' un access token dal refresh token gia' emesso per l'MCP e si POSTa

    https://script.googleapis.com/v1/scripts/<SCRIPT_ID>:run
    {"function":"exec","parameters":["mail.send", "<json>"]}

che dispaccia a `mailSend_(p)` in Code.gs.

Solo stdlib, gira sotto /usr/bin/python3 (3.9.6). Best-effort: esce 0 se manda,
diverso da zero altrimenti, cosi' il chiamante puo' fare `|| log` senza che una
mail persa faccia mai cadere una traduzione.

    notify_gas_mail.py --to a@b.com --subject "..." [--body "..."]
    (senza --body il corpo si legge da stdin)

**Configurazione (questo repo e' pubblico: qui non si scrive nulla di personale).**
`GAS_DIR` (la dir con credentials.json + token.json) e `WILIGELMO_GAS_SCRIPT_ID`
si prendono dall'ambiente, oppure da `scripts/translate/.gas_env` -- che e'
gitignorato apposta. Formato del file: `CHIAVE=valore` per riga.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, ".gas_env")


def _conf(key):
    """Ambiente, poi .gas_env. Niente default hardcoded: un percorso personale o
    uno script id in un repo pubblico e' esattamente cio' che si evita."""
    if os.environ.get(key):
        return os.environ[key]
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln or ln.startswith("#") or "=" not in ln:
                    continue
                k, _, v = ln.partition("=")
                if k.strip() == key:
                    return v.strip().strip("\"'")
    return None


def _post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _access_token(gas_dir):
    with open(os.path.join(gas_dir, "credentials.json"), encoding="utf-8") as fh:
        creds = json.load(fh)["installed"]
    with open(os.path.join(gas_dir, "token.json"), encoding="utf-8") as fh:
        tok = json.load(fh)
    body = urllib.parse.urlencode({
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": tok["refresh_token"],
        "grant_type": "refresh_token",
    }).encode("utf-8")
    res = _post(creds["token_uri"], body,
                {"Content-Type": "application/x-www-form-urlencoded"})
    return res["access_token"]


def send(to, subject, body):
    gas_dir = _conf("GAS_DIR")
    script_id = _conf("WILIGELMO_GAS_SCRIPT_ID")
    if not gas_dir or not script_id:
        raise RuntimeError("GAS_DIR / WILIGELMO_GAS_SCRIPT_ID non configurati "
                           "(ambiente o %s)" % ENV_FILE)
    at = _access_token(gas_dir)
    payload = json.dumps({
        "function": "exec",
        "parameters": ["mail.send",
                       json.dumps({"to": to, "subject": subject, "body": body})],
        # devMode: gira l'ultimo codice salvato, senza bisogno di un deployment
        "devMode": True,
    }).encode("utf-8")
    url = "https://script.googleapis.com/v1/scripts/%s:run" % script_id
    res = _post(url, payload,
                {"Authorization": "Bearer " + at, "Content-Type": "application/json"})
    # scripts.run torna una Operation: le eccezioni dello script arrivano come
    # "error" di primo livello, non come HTTP non-200.
    if res.get("error"):
        raise RuntimeError("scripts.run error: " + json.dumps(res.get("error"))[:600])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", default=None)
    a = ap.parse_args()
    body = a.body if a.body is not None else sys.stdin.read()
    try:
        send(a.to, a.subject, body)
    except Exception as e:      # best-effort: non far mai cadere il chiamante
        sys.stderr.write("notify_gas_mail: FALLITA: %s\n" % e)
        return 1
    print("notify_gas_mail: inviata a %s" % a.to)
    return 0


if __name__ == "__main__":
    sys.exit(main())
