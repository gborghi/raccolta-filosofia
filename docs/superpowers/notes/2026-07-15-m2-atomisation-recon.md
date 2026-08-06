# M2 — ricognizione per l'atomizzazione

**Fatta PRIMA di scrivere il piano.** È la lezione di M1a: il localizzatore, sondato sui file veri prima della stesura, ha retto (116/116); lo stripper, scritto da una fixture inventata, è crollato.

## Il corpus

| | |
|---|---|
| Opere | 115 (8 filosofi) |
| Parole | **9.062.412** |
| Più grande | `Hume/THE_HISTORY_OF_ENGLAND` — 1.168.711 parole |
| Poi | `Marx/CAPITAL` 837k · `Hegel/The_Philosophy_of_Fine_Art` 623k · `Hegel/Lectures_on_the_History_of_Philosophy` 509k |

## La scoperta

Cercando marker strutturali (`CHAPTER`, `BOOK`, `LETTER`, `SECTION`, numerazione romana) **54 opere su 115 non ne hanno nessuno** — comprese le `MORAL_EPISTLES` di Seneca, che sono 124 lettere.

Non sono prive di struttura: **portano il proprio `CONTENTS`**, che elenca le parti con i titoli.

```
Seneca/THE_MORAL_EPISTLES        Locke/MISCELLANEOUS_LETTERS      Hegel/Phenomenology
  Introduction                     TO KING CHARLES II.              Preface: On Scientific Knowledge
  I. On Saving Time                TO THE D. OF YORK.               Introduction
  II. On Discursiveness…           MR. LOCKE TO MR. MOLYNEUX.       A. Consciousness
  III. On True and False…          MR. MOLYNEUX TO MR. LOCKE.       I. CERTAINTY AT THE LEVEL OF…
```

Il `CONTENTS` è sopravvissuto perché in M1a l'abbiamo classificato come materiale d'autore (è dell'edizione originale, PD) e il taglio del blurb si ferma lì. Quella decisione, presa per ragioni di copyright, ci regala ora la struttura.

## Il design: lo stesso algoritmo di M1a, un livello più giù

M1a: TOC del volume → localizza ogni opera nel corpo → span fra header consecutivi.
M2: CONTENTS dell'opera → localizza ogni parte nel corpo → span fra header consecutivi.

Il codice esiste già ed è validato:

| M1a | M2 |
|---|---|
| `parse_toc` (vocabolario chiuso di sezioni) | parse del `CONTENTS` dell'opera |
| `body_search_start` (dopo il colophon) | dopo il blocco `CONTENTS` |
| `is_toc_occurrence` (il successore è un altro titolo) | **identico** |
| `find_body_line` con `start` avanzante | **identico** |
| span fra header consecutivi | **identico** |

I due filtri che sono costati sangue in M1a valgono qui uguali:
- **ordine** — senza, `I. On Saving Time` si aggancia alla prima ricorrenza, non alla sua;
- **successore** — distingue la voce d'indice dall'header vero.

## Rischi — verificati sul corpus vero

| | misurato |
|---|---|
| Opere **con** `CONTENTS` | **95 / 115** |
| Voci d'indice totali | **3.824** |
| Parole medie per voce | **2.304** (~3k token — vicino al target di 1000-2000) |
| Opere **senza** `CONTENTS` | **20**, tutte piccole (max 78k parole) |

Le 20 senza indice sono lettere e opuscoli brevi — `Locke/SOME_THOUGHTS_CONCERNING_EDUCATION` (78k), `Locke/A_LETTER_CONCERNING_TOLERATION_1689` (20k), `Marx/NOTES_ON_ADOLPH_WAGNER` (12k), `Pascal/Thoughts_on_the_Jesuits` (8k). Fallback: marker strutturali (`CHAPTER`/`SECTION`/`LETTER`), altrimenti atomo unico. Nessuna è grande abbastanza da essere un problema.

Rischi che restano da gestire nel piano:

| rischio | mitigazione |
|---|---|
| Voci d'indice non localizzabili nel corpo | riusare il pattern `unmarked` di M1a: se non localizzo, **non spezzo** — l'opera resta intera invece di essere tagliata a caso |
| Voci troppo grandi | ~2,3k parole in media, ma la coda lunga va spezzata per paragrafo fino al target |
| Voci che sono intestazioni di gruppo | `A. Consciousness` in Hegel non è una parte, è un raggruppamento: span quasi nullo → fondere con la voce successiva |
| `LIST_OF_LATIN_TEXTS` | 379k parole: va splittato per opera e appaiato all'inglese via la mappa nel suo `CONTENTS` (spec, sezione multilingua) |

## Target

Atomi di ~1000-2000 token. Con 9M parole → ~12M token → **~8.000 atomi** dopo lo split della coda lunga. Sotto il cap file di Cloudflare **solo** grazie a `SPA=1` — una pagina per opera, atomi instradati client-side — esattamente come English, che con ~15k unità sta a ~7,8k file.
