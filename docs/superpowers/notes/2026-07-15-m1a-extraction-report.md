# M1a — report di estrazione

**Data:** 2026-07-15
**Comando:** `python -m scripts.extract.run` → exit 0
**Suite:** 51 test verdi

## Risultato

```
OK   seneca       26/26 opere
OK   pascal       12/12 opere
OK   marx         19/19 opere
OK   hegel        8/8 opere
OK   kant         16/16 opere
OK   hume         12/12 opere
OK   locke        18/18 opere
OK   lucretius    4/6 opere (2 skip)
```

**115 file** in `VaultPhilosophy/Philosophers/<Nome>/_raw/`, **52MB**. Nessun `FAIL`, nessuna opera `unmarked`, nessun blurb editoriale rilevato nell'output.

Seneca fa 26 perché include la sezione dei testi latini originali (`kind: latin`) oltre alle 25 opere tradotte.

## Ispezione a campione (obbligatoria)

| opera | inizia | finisce |
|---|---|---|
| `Seneca/ON_THE_SHORTNESS_OF_LIFE` | `CONTENTS` | i funerali di Sesto Turannio — chiusa autentica del *De brevitate vitae* |
| `Hegel/The_Phenomenology_of_Spirit` | `CONTENTS` | *"The chalice of this realm of spirits / Foams forth to God His own Infinitude"* — versi finali della Fenomenologia |
| `Hume/A_TREATISE_OF_HUMAN_NATURE` | `CONTENTS` | la confessione degli errori nell'Appendice |

Frontmatter completo su tutte e tre. Nessun blurb Delphi in testa, nessuna coda di apparato.

## Cosa è servito davvero

Il piano iniziale è stato riscritto due volte, e in entrambi i casi perché è stato verificato sui file veri **prima** di scrivere il codice.

**Il localizzatore.** L'euristica pianificata ("l'header di corpo è seguito da prosa entro 20 righe") era sbagliata su due fronti:
- `ON ANGER` in Seneca è seguito da `Translated by Aubrey Stewart` e da un **indice interno all'opera** — la prosa arriva decine di righe dopo. Falso negativo.
- `AGAMEMNON` e `OEDIPUS` venivano agganciati **dentro** `THE TROJAN WOMEN` e `THE PHOENICIAN WOMEN`: sono nomi di personaggi nelle battute delle tragedie.

Sostituita da tre filtri: posizionale (dopo il colophon), successore (la riga dopo una voce di TOC è un altro titolo), ordinato (ogni ricerca parte dopo la precedente). Risultato: 116/116 header localizzati, offset monotoni.

**Lo strip del blurb.** Il design a regola è fallito del tutto:
- 42 opere su 116 non hanno `Translated by` — Hume, Locke e Marx scrivevano in inglese — e la funzione restituiva il corpo intatto.
- Le altre 74 hanno 0–4 paragrafi di blurb; ne toglieva uno.
- I test passavano perché la fixture era inventata.

Nessuna regola posizionale regge: gli stessi paragrafi lunghi in testa sono blurb Delphi in `hume/A TREATISE` e la **prefazione autentica di Hume** in `hume/AN ABSTRACT`. Sostituito da una passata di lettura una-tantum (subagent della sessione, nessuna API), il cui output è `data/work_starts.json` — offset fissi committati. Build e test non chiamano alcun LLM.

## Scoperte dalla passata

- **Le opere vere sono 114, non 116.** `lucretius/The Latin Text` e `The Dual Text` sono divisori di sezione Delphi: span di 12 righe con una sola didascalia. Marcati `skip`.
- **`hume/THE HISTORY OF ENGLAND` e `kant/PERPETUAL PEACE`**: il blurb superava la finestra di 45 righe. I lettori hanno segnalato *incerto* invece di indovinare — il design ha funzionato. Verificati a mano, entrambi tagliano a `CONTENTS`.
- **La sezione latina di Seneca era invisibile**: `dump_heads` estraeva solo `kind == "work"`, ma `extract()` pubblica anche `kind == "latin"`. Corretto.

## Difetto trovato dopo il primo "verde"

**63 opere su 115 contenevano i marker di `grouptxt.sh`** — `===== INIZIO FILE: … =====` e `===== FINE FILE: … =====`, residui dello script che ha concatenato i chunk del publisher nei blob `*_partN.txt`. Spazzatura di formato finita dentro le opere.

Non l'hanno preso né il piano, né i reviewer per-task, né la review finale, né le mie ispezioni a campione. Il motivo è preciso e vale più del difetto: **ho ispezionato testa e coda, e i marker stanno in mezzo.** Il campione era mal disegnato, non troppo piccolo. Cercarli è costato un `grep`; li ho trovati solo perché sondando Cartesio per M1b me li sono visti passare davanti.

Corretto in `load_raw` (`common.py`) — il punto per cui passa ogni adapter, quello Delphi e i cinque bespoke di M1b. Verificato: 0 marker residui, run 8/8, 60 test.

**Regola per M1b:** ispezionare il **centro** delle opere, non solo gli estremi.

## Limiti noti (aperti)

| | |
|---|---|
| Didascalie dopo il CONTENTS | Alcune didascalie Delphi stanno **dentro** l'opera, dopo il suo indice: un taglio singolo non le toglie (`marx/Jewish Question`, `Eighteenth Brumaire`, `pascal`). Sono righe singole fattuali, non paragrafi di blurb. Da ripulire in M2. |
| Latino come blocco unico | `seneca/LIST OF LATIN TEXTS` è un blocco di ~34k righe con tutte le opere latine, non una per opera. Lo split spetta a M2 — e il suo `CONTENTS` contiene già la mappa (`THE MADNESS OF HERCULES — Hercules Furens`). |
| `traduttore` duplicato | `seneca/ON ANGER` ha `first_line: ""` e il corpo comincia con `Translated by Aubrey Stewart`, che ripete il frontmatter. Cosmetico. |
| `TOC_END` | Un titolo che iniziasse con `Version` o `©` troncherebbe il TOC. Verificato: 0 casi su 149 titoli. Rischio di forma, non di sostanza. |

## Prossimo

M1b: adapter bespoke — `cartesio`, `rousseau`, `nietzsche` (epub tedesco), `ortega`, `aquinas` (epub Summa). La lezione da portare: **validare sui file veri prima di scrivere il piano**. Il localizzatore, validato in anticipo, ha retto; lo stripper, scritto da una fixture, no.
