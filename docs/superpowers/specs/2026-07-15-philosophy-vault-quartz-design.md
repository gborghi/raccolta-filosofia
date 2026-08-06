# Philosophy — Vault Obsidian + sito Quartz v5

**Data:** 2026-07-15
**Stato:** design, in attesa di approvazione
**Modello:** `../English` (VaultEnglish + quartz-eng-lit)

## Cosa costruiamo

Pipeline in due parti, sul modello di `../English`:

- `VaultPhilosophy/` — vault Obsidian, fonte di verità. `Knowledge Graph/` (Opere, Assi, Posizioni, Argomenti, Scuole, Forme, Concetti, Figure, Clusters) + `Philosophers/<Nome>/` (`_raw/`, `Atomized/`).
- `quartz-philosophy/` — SSG Quartz v5, repo git, deploy su GitHub Pages.

Differenza portante rispetto a English: lì i tag stanno sull'**opera**; qui le posizioni filosofiche si taggano sul **brano atomizzato**, perché un filosofo cambia posizione tra opere e a volte dentro la stessa.

## Decisioni prese

| Decisione | Scelta | Nota |
|---|---|---|
| Lingua | Originale dell'edizione | `lang:` per nota. EN×10, DE Nietzsche, FR Rousseau, ES Ortega |
| Copyright | **Tutte le fonti sono PD.** Nessuna guardia, mai | Risolto risalendo agli originali. Vedi sotto |
| Filosofi | **12** (Dávila escluso) | Unica fonte protetta; rimosso su decisione dell'utente |
| Apparati editoriali | **Non pubblicati** | Introduzioni, note del curatore, cronologie, cataloghi. Solo testo nudo |
| Traduzioni | Rimandate a milestone successiva | IT+EN nostre, poi guardia sulle vecchie traduzioni in copyright |
| Modello tagging | `claude-opus-4-8` via Batch API | ~$119 sul corpus intero |
| Fonte | `*_partN.txt` (concat `grouptxt.sh`) | Copre tutto; ignoro i "Parte NN di 40" |

### Copyright — risolto alla fonte

**Nessuna opera pubblicata è protetta. Non serve alcuna guardia.**

Il copyright segue chi ha scritto quelle parole — non l'editore, e non la data di morte dell'autore del pensiero. Due mosse hanno chiuso il problema:

1. **Niente apparati editoriali.** Per un testo PD ripubblicato, l'apparato (introduzioni, note del curatore, blurb, cronologie, cataloghi) è l'unica cosa rivendicabile. Toglierlo lascia l'editore senza appigli: questo copre Delphi ×8, OPU (Cartesio), Arvensa (Rousseau), Fundación Ortega.
2. **Nietzsche dall'originale tedesco.** La traduzione italiana Newton Compton 2012 era protetta fino agli anni '80 del secolo. L'alternativa inglese (edizione Levy 1909-13) è PD a macchia di leopardo — Common e Zimmern sì, ma **Ludovici († 1971) copre Ecce Homo, Götzen-Dämmerung, Antichrist e Will to Power fino al 2042**. L'originale tedesco (Nietzsche † 1900, PD dal 1971) elimina del tutto l'opera derivata. Anaconda Verlag dichiara `Alle Rechte vorbehalten` ma è boilerplate su testo PD; §70 UrhG (edizioni scientifiche, 25 anni) richiede lavoro critico-filologico che una ristampa popolare non ha.
3. **Dávila escluso.** Le traduzioni italiane (Krisis) erano l'unica fonte residua protetta e non esiste originale accessibile. Rimosso dal progetto su decisione dell'utente — come `EXCLUDE_AUTHORS` per Hemingway in English.

Il frontmatter porta comunque `edizione:`/`traduttore:`/`anno_edizione:`/`pd_year:`: non più per una guardia, ma come provenienza citabile. Costa zero adesso e non è ricostruibile dopo.

**Conseguenza:** M6 (traduzioni) non ha più una motivazione legale. Resta un miglioramento di fruibilità — le nostre traduzioni IT/EN rendono leggibili tedesco, francese e spagnolo — non un requisito.

## Le fonti

| Filosofo | Edizione | Lingua | Confini opera |
|---|---|---|---|
| seneca, pascal, marx, hegel, kant, hume, locke, lucretius | Delphi Classics | EN | TOC `Contents` in testa → adapter unico |
| cartesio | OPU 2019 | EN | bespoke |
| rousseau | Arvensa "93 titres" | FR | bespoke, TOC Arvensa |
| **nietzsche** | **Anaconda Verlag 2013, epub, originale tedesco** | **DE** | **epub, 7 opere dal TOC NCX** |
| ortega | Obras completas, 5 tomi | ES | bespoke, TOC per tomo |
| aquinas | epub Summa Theologiae | EN | struttura quaestio/articulus |

**Nietzsche** — l'epub `Gesammelte Werke` è titolo di marketing: contiene 7 opere, non l'opera omnia. Die Geburt der Tragödie · Menschliches, Allzumenschliches [Erster Band] · Also sprach Zarathustra · Zur Genealogie der Moral · Götzen-Dämmerung · Der Antichrist · Ecce Homo. Mancano *Jenseits von Gut und Böse*, *Die fröhliche Wissenschaft*, *Morgenröte*, *Menschliches II* — reperibili PD su Gutenberg/zeno.org se si vorrà completare.

**Dávila** — escluso. Vedi sezione copyright.

Corpus: ~17.5M parole (~24M token), ~26M con la Summa.

## Un'opera può avere più lingue, con il bottone di selezione

Dove la fonte porta più rappresentazioni della stessa opera, **si pubblicano tutte**, appaiate, con il selettore di lingua (lo stesso pattern qlang bilingue di English).

Il caso concreto è già estratto in M1a: Delphi ship Seneca e Lucrezio con **gli originali latini** accanto alle traduzioni inglesi (`kind: latin`). E l'accoppiamento non va indovinato — Delphi lo dichiara nel `CONTENTS` della sezione latina, elencando ogni testo col titolo inglese davanti:

```
THE MADNESS OF HERCULES — Hercules Furens
THE TROJAN WOMEN — Troades
TO MARCIA, ON CONSOLATION — Ad Marciam, De consolatione
```

È la chiave di join, gratis. Lucrezio ha anche un `DUAL LATIN AND ENGLISH TEXT` (testo a fronte).

Conseguenze:
- **M2** deve splittare `seneca/LIST OF LATIN TEXTS` (blocco unico di ~34k righe) per opera usando quella mappa, e appaiare ogni latino alla sua traduzione via ID di opera.
- **M4** rende il selettore: stessa pagina, `lang` commutabile fra le rappresentazioni disponibili.
- Il latino è PD (Seneca † 65 d.C., Lucrezio † 55 a.C.): nessun problema di diritti, solo la nota di navigazione Delphi in testa, già tagliata.
- Vale anche per M6: le traduzioni nostre IT/EN diventano rappresentazioni aggiuntive dello stesso ID di opera, non pagine separate.

## Il grafo è language-agnostic (requisito portante)

**Deve essere possibile cercare i concetti di Nietzsche in inglese benché il testo sia in tedesco.** Vale per la ricerca, i link e tutti gli aggregatori.

Questo funziona solo se il vocabolario aggregatore è **canonico e indipendente dalla lingua della fonte**. Un brano tedesco non si trova cercando "eternal recurrence" perché contenga quelle parole — si trova perché è **taggato con un ID di concetto canonico**, e quell'ID ha un'etichetta inglese. Il testo resta in lingua originale; il grafo no.

Conseguenze vincolanti:

- **Ogni nodo aggregatore ha un ID canonico** (slug stabile, `eternal_return`) e **etichette bilingui** `label_it` / `label_en` nel frontmatter. L'ID non cambia mai; le etichette sono per gli umani.
- **Entrambe le etichette vanno nell'indice di ricerca**, più eventuali alias (`ewige Wiederkunft`, `eterno ritorno`, `eternal recurrence`). Un asse/posizione/concetto è raggiungibile da qualsiasi lingua.
- **I wikilink puntano all'ID**, non all'etichetta — altrimenti cambiare una traduzione romperebbe il grafo.
- **Il tagging (M3) emette ID**, mai testo libero. Il prompt riceve il vocabolario controllato e sceglie da quello: è anche ciò che rende confrontabili Nietzsche in tedesco e Hume in inglese sullo stesso asse.
- La lingua del **testo** (`lang:`) e la lingua delle **etichette** sono cose diverse e non vanno confuse.

Questo è il motivo per cui il grafo è costruito su un vocabolario controllato invece che su keyword estratte dal testo: le keyword sono prigioniere della lingua della fonte, gli ID no.

## Aggregatori

Nove tipi di nodo. Il cuore è la coppia **Assi ↔ Posizioni**.

Un **Asse** è una domanda filosofica; una **Posizione** è una risposta. Ogni brano è taggato con la posizione che difende. La pagina di un asse diventa uno spettro: domanda in cima, posizioni schierate, sotto ogni posizione i filosofi coi brani come prove. `contro:` nel frontmatter rende esplicito il conflitto.

Le Posizioni sono **a due livelli**: famiglia → sfumatura, via `variante_di:`. `empirismo` è la famiglia; `empirismo scettico` (Hume) e `empirismo moderato` (Locke) le sfumature.

### I 14 assi

| Asse | Posizioni |
|---|---|
| Origine della conoscenza | innatismo · empirismo · razionalismo · scetticismo · criticismo trascendentale |
| Statuto del reale | atomismo · idealismo · materialismo · dualismo · realismo delle idee |
| Universali | realismo · concettualismo · nominalismo |
| Libertà e necessità | libero arbitrio · determinismo · compatibilismo · fato e provvidenza · clinamen |
| Fondamento della morale | legge naturale · imperativo del dovere · virtù · utile e piacere · sentimento morale · volontà di potenza |
| Anima e corpo | dualismo sostanziale · ilemorfismo · materialismo · monismo |
| Dio | teismo dimostrativo · fideismo · deismo · panteismo · ateismo · genealogia critica |
| Legittimità del potere | contratto sociale · volontà generale · diritto naturale · conflitto di classe · autorità tradizionale |
| Senso della storia | provvidenza · progresso · dialettica dello spirito · materialismo storico · eterno ritorno · decadenza |
| Natura umana | bontà naturale · peccato originale · miseria e grandezza · tabula rasa · animale sociale · uomo-massa |
| Fine della vita | atarassia · apatheia · beatitudine · piacere · vita come progetto |
| Metodo | dubbio metodico · quaestio disputata · dialettica · induzione · genealogia · raziovitalismo |
| Tempo e morte | brevità della vita · memento mori · eternità · eterno ritorno · storicità |

### Gli altri tipi

- **Argomenti** — cogito, scommessa di Pascal, quinque viae, argomento ontologico, imperativo categorico, dialettica servo-padrone, clinamen, feticismo delle merci, problema dell'induzione, stato di natura. Frontmatter: premesse → conclusione, chi lo avanza, chi lo attacca.
- **Scuole** — stoicismo, epicureismo, scolastica, razionalismo continentale, empirismo britannico, idealismo tedesco, materialismo storico, illuminismo, tradizionalismo reazionario, raziovitalismo. Aggregatore genealogico, ortogonale agli assi.
- **Forme** — epistola (Seneca), quaestio/articulus (Aquinas), pensée (Pascal), aforisma (Nietzsche), escolio (Dávila), poema didascalico (Lucrezio), meditazione (Cartesio), trattato, dialogo, saggio.
- **Concetti** — sostanza, causa, virtù, plusvalore, noumeno, grazia, alienazione, cogito, volontà.
- **Figure** — interlocutori citati/attaccati non autori del vault (Platone, Aristotele, Epicuro, Spinoza) + personae (Zarathustra, genio maligno, Lucilio).
- **Clusters** — comunità Louvain, calcolate.

## Architettura

### 1. Estrazione (`scripts/extract/`)

Un **adapter per edizione**, interfaccia comune:

```
adapter(rawText) -> [{ title, start, end, kind }]
```

- `delphi.py` — copre 8 filosofi. Parsa il TOC `Contents`, mappa ogni entry alla sua occorrenza nel corpo. Le sezioni `The Biography`, `The Delphi Classics Catalogue` sono apparato → scartate. `The Latin Texts` (Seneca, Lucrezio) → conservate come rappresentazione separata.
- `davila.py` — i marker `INIZIO FILE` sono i confini. Banale.
- `nietzsche.py`, `ortega.py`, `rousseau.py`, `cartesio.py` — bespoke.
- `aquinas.py` — epub → quaestio/articulus.

Output: `VaultPhilosophy/Philosophers/<Nome>/_raw/<OPERA>.md`, un file per opera. Da qui in poi la pipeline è identica a English.

**Questo è il pezzo a rischio più alto.** In English lo split era già fatto a monte; qui è il lavoro. Ogni adapter va verificato contro il TOC atteso (conteggio opere) prima di procedere.

### 2. Atomizzazione

`_raw/<OPERA>.md` → `Atomized/<OPERA>/<unità>.md`. Unità: capitolo, lettera, quaestio, aforisma, pensée, libro — secondo la forma. Target ~1000-2000 token per unità.

### 3. Tagging (`scripts/tag/`)

Batch API, `claude-opus-4-8`, structured outputs. Per brano: assi+posizioni, concetti, argomenti, figure citate.

Prompt caching **obbligatorio**: la tassonomia (~8k token) × ~17k brani = 136M token, cinque volte il corpus. `cache_control` sull'ultimo blocco system. Scaldare la cache con una richiesta singola prima del batch (le entry sono leggibili solo dopo che la prima risposta inizia a streammare; il batch parallelizza).

Output → `data/atom_tags.json`, consumato da `preprocess.mjs`.

### 4. Sito (`quartz-philosophy/`)

Clone dell'architettura English: `preprocess.mjs` emette shell markdown sottili con mount `<div id=...>` + JSON grasso in `quartz/static/`; tutto renderizzato client-side.

- `SPA=1` obbligatorio — una pagina per opera, atomi dietro marker, routing client-side (`atomRouter.inline.ts`). Tiene il conteggio file sotto il cap di Cloudflare.
- Pagine generate: `index.md`, `opere.md`, `cerca.md`, `assi.md`, `naviga.md`, `brani.md`.
- Componenti riusati da English: `opereTable`, `braniTable`, `cerca`, `relatedWorks`, `conceptWorks`, `atomRouter`/`spa`, `sidebarToggle`, `searchLoading`, `qtable.ts`.
- Nuovo: `desk.inline.ts` (sostituisce `radialWheel`), `axisSpectrum.inline.ts` (lo spettro di un asse).
- Build: `SPA=1 node preprocess.mjs` → `npx quartz plugin restore` → `NODE_OPTIONS=--max-old-space-size=14336 npx quartz build` → mobile index → compress search → slim tags. CI **non** esegue preprocess: si committa `content/` rigenerato.

### 5. Homepage — la scrivania

Sostituisce la wheel di English. Un piano di scrivania (immagine generata con Recraft: legno/cuoio, luce laterale) con **emblems** — quadrati a bordo smussato (`border-radius` ~12px) — sparsi come carteggi, con leggere rotazioni. Emblems per i 13 filosofi (ritratti) e per i concetti principali.

## Tema

- Palette: `#D90000` · `#FFEA93` · `#8DB355` · `#000000`
- Font: **Damion** (titolo), **Josefin Slab** (headings minori), **Martel** (testo)

## Milestone

| # | Milestone | Stato | Contenuto |
|---|---|---|---|
| **M1a** | **Estrazione Delphi** | **fatto** | 8 filosofi, 115 opere, 52MB. Confine copyright fail-closed |
| M2 | Atomizzazione | prossimo | `_raw` → `Atomized/`, per forma |
| M3 | Grafo | | tassonomia, tagging, note aggregatore, clusters Louvain |
| M4 | Sito | | Quartz v5, preprocess, SPA, tabelle, ricerca TF-IDF, Cloudflare |
| M5 | Homepage | | scrivania Recraft, emblems, spettri degli assi |
| M1b | Adapter bespoke | rimandato | cartesio, rousseau, nietzsche, ortega, aquinas |
| M6 | Traduzioni | | IT+EN nostre |

### Perché M1b viene dopo il sito

L'ordine originale era M1 completo → sito. Sondando le fonti bespoke il quadro è cambiato:

| fonte | righe | struttura |
|---|---|---|
| cartesio | 5.318 | 1 `Contents` piatto, 8 opere — trattabile |
| rousseau | 162.275 | **853** `TABLE DES MATIÈRES`, 93 titoli |
| ortega | 292.028 | 55 `Índice`, 5 tomi |

Sono ~460k righe in quattro lingue, ognuna con una struttura sua: cinque progetti, non cinque funzioni. Costruirle tutte prima del sito significa mesi senza niente di visibile, e senza aver mai provato che l'architettura Quartz regge su questo corpus.

**Le 115 opere estratte sono già un corpus vero.** Il sito si costruisce su quelle; gli altri quattro filosofi si aggiungono dopo, entrando nella stessa pipeline (`_raw/<OPERA>.md` + `work_starts.json`) senza toccare nulla a valle. Un sito funzionante con 8 filosofi vale più di una pipeline ferma con 12.

### Tagging: livello opera prima, livello brano dopo

Lo spec vuole i tag sul **brano** (un filosofo cambia posizione fra le opere e dentro un'opera). Resta l'obiettivo. Ma il tagging gira sull'abbonamento Claude Code, non sull'API: ~17k brani non sono praticabili come subagent.

Quindi M3 tagga prima a **livello di opera** (115 elementi — la stessa scala della passata sui confini, che ha funzionato). Dà aggregatori reali e un sito completo. Il raffinamento per-brano è un incremento successivo sulla stessa tassonomia e sugli stessi ID: nessuna riscrittura, solo tag più fini.

## Gotcha d'ambiente (da English, valgono qui)

- **Python:** `python`/`python3` in Bash è uno stub rotto del Windows Store. Usare `C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe`.
- **Dropbox:** l'albero è dentro Dropbox. `node_modules/`, `public/`, `.quartz/` vanno marcati `com.dropbox.ignored` (NTFS ADS). Fermare la sync durante rigenerazioni grosse.
- **git ignorecase:** il content è emesso lowercase; un rename di sole maiuscole non viene tracciato.
- **Mai Gemini.** Subagent istruiti in caveman style.

## Rischi

| Rischio | Mitigazione |
|---|---|
| Confini opera sbagliati (5 adapter bespoke) | Verifica per fonte contro conteggio TOC atteso prima di procedere |
| Apparato non rimosso del tutto | Il TOC Delphi nomina le sezioni apparato esplicitamente; per le altre, ispezione manuale |
| Posizioni filosofiche mal attribuite | Opus 4.8; il prompt deve distinguere "difende" da "espone per confutare" |
| Cache non scatta (min 4096 token su Opus) | Tassonomia ~8k, sopra soglia. Verificare `cache_read_input_tokens` > 0 |
| Build OOM | `--max-old-space-size=14336`, SPA obbligatorio |
