#!/usr/bin/env bash
# Coda di traduzione dell'intero repo, un autore alla volta, dal piu' corposo al
# piu' corto. Pensato per girare STACCATO dalla sessione che lo lancia:
#
#     cd quartz-philosophy/scripts/translate
#     nohup ./run_queue_all.sh > run_logs/queue.log 2>&1 &
#     disown
#
# Ogni autore e' un processo a se': se uno muore, la coda prosegue col successivo
# invece di fermarsi tutta. Riprendibile — un atomo che ha gia' il suo sibling non
# viene mai riconsiderato, quindi rilanciare lo script riprende da dov'era.
#
# Per uccidere: `kill <PID>` sul PID esatto stampato in testa al log. Mai
# `pkill -f`, che qui prenderebbe anche altri python di passaggio.
set -u
cd "$(dirname "$0")"

PY="${PY:-/usr/bin/python3}"
export HY_WORKERS="${HY_WORKERS:-4}"

# Ordine per mole di lavoro residuo, misurato il 2026-08-06. "Ortega y Gasset"
# ha degli spazi nel nome: l'array e' l'unico modo di passarlo intero.
# Ortega escluso: tradotto per intero (IT+EN) il 2026-08-08 con DeepSeek, non
# ha piu' arretrato per HY. Rilanciare con `./run_queue_all.sh "Ortega y Gasset"`
# per ripescare eventuali rifiuti.
AUTHORS=(
  Augustine Aquinas Rousseau Locke Descartes Marx Hegel
  Hume Seneca Aristotle Schopenhauer Hobbes Kant Nietzsche Spinoza
  Pascal Plato Leibniz Lucretius
)
if [ "$#" -gt 0 ]; then
  AUTHORS=("$@")
fi

echo "=== coda traduzioni avviata $(date '+%Y-%m-%d %H:%M:%S') — PID $$ ==="
echo "=== worker: $HY_WORKERS — autori: ${#AUTHORS[@]} ==="

# Il server HY deve rispondere prima di cominciare: senza, ogni atomo fallirebbe
# tre volte con backoff e la coda macinerebbe scarti per ore.
if ! curl -sf --max-time 10 http://localhost:1234/v1/models > /dev/null; then
  echo "!! LM Studio non risponde su :1234 — coda non avviata"
  exit 1
fi

for a in "${AUTHORS[@]}"; do
  echo
  echo "--- $a — $(date '+%H:%M:%S') ---"
  "$PY" run_author_hy.py "$a" || echo "!! $a terminato con errore, proseguo"
done

echo
echo "=== coda conclusa $(date '+%Y-%m-%d %H:%M:%S') ==="
"$PY" notify_gas_mail.py --to "${TRANSLATE_MAIL_TO:-gio.borghi@gmail.com}" \
  --subject "[filosofia] coda traduzioni conclusa" \
  --body "La coda ha finito tutti gli autori in lista.

Controlla i rifiuti in scripts/translate/run_logs/rejected.jsonl: restano senza
traduzione e vengono ripescati rilanciando lo stesso autore.

Verifica finale:  python3 scripts/translate/verify.py" || true
