# Regole di traduzione degli atomi

Ogni atomo del sito deve essere leggibile in **italiano e inglese**, più la
**lingua originale** se diversa da IT/EN. Una traduzione è un **file sibling**
accanto all'originale:

```
.../ON_PROVIDENCE/002_II.md      <- fonte (qui inglese)
.../ON_PROVIDENCE/002_II.it.md   <- traduzione italiana
.../ON_PROVIDENCE/002_II.en.md   <- traduzione inglese (solo se la fonte NON e' gia' inglese)
```

Il nome è quello della fonte con `.md` sostituito da `.it.md` o `.en.md`.
Nient'altro. Non si crea nessuna directory, non si tocca mai il file di
partenza.

Quali file servono, secondo la lingua della fonte (campo `lang` del frontmatter):

| fonte  | servono                | lingue mostrate |
|--------|------------------------|-----------------|
| `en`   | `.it.md`               | EN (fonte) + IT |
| `it`   | `.en.md`               | IT (fonte) + EN |
| altra (`es`/`de`/`fr`/`la`/`grc`) | `.en.md` **e** `.it.md` | originale + EN + IT |

Non si emette mai un sibling nella stessa lingua della fonte (un `.en.md`
accanto a una fonte inglese sarebbe un doppione).

## Perché sibling e non un file unico per opera

`preprocess.mjs` accoppia i sibling **per nome**, atomo per atomo, e li emette
dentro l'unica pagina SPA dell'opera, ciascuna traduzione dietro un marker
`<span class="qlang-split" data-lang="it">` / `data-lang="en"`. Il lettore
`atomRouter` partiziona il DOM su quei marker e mostra i bottoni di lingua (due
o tre) solo per le lingue effettivamente presenti nell'opera.

Ne segue la proprietà che conta: **le traduzioni sono indipendenti**. Un atomo
tradotto male resta un atomo sbagliato; non fa saltare l'opera. Per lo stesso
motivo un'opera tradotta a metà è pubblicabile — gli atomi senza `.it.md`
mostrano "traduzione non disponibile per questa sezione" e basta. Non c'è
nessuna soglia da raggiungere prima di pubblicare.

## Frontmatter

Il `.it.md` porta un frontmatter ridotto. `preprocess.mjs` ne usa solo il corpo:
il frontmatter serve alla verifica automatica, che controlla che la traduzione
sia agganciata all'atomo giusto.

```yaml
---
philosopher: "Seneca"
lang: "it"
work: "ON_PROVIDENCE"
atom_n: 2
---
```

`philosopher`, `work` e `atom_n` si copiano **identici** dalla fonte — sono
chiavi, non prosa: non si traducono. `lang` è `"it"` nel `.it.md` e `"en"` nel
`.en.md`. Gli altri campi della fonte (`edizione`, `traduttore`, `pd_year`,
`source_key`, `atom_title`, `kind`) non vanno riportati: descrivono l'edizione
di partenza, e ripeterli nella traduzione significherebbe attribuire il testo
tradotto al traduttore dell'edizione fonte.

## Wikilink: la regola che conta

Il testo contiene wikilink al vocabolario controllato, messi da
`scripts/link/run.py`:

```markdown
WE are determined by [[custom|CUSTOM]] alone to suppose the future conformable
to the past.
```

La forma è `[[bersaglio|etichetta]]`. **Il bersaglio è un ID canonico e non si
tocca mai. L'etichetta è prosa e si traduce.**

```markdown
Siamo determinati dalla sola [[custom|CONSUETUDINE]] a supporre il futuro
conforme al passato.
```

`custom` resta `custom` anche in italiano. È questo che rende il grafo
language-agnostic: `[[custom|CUSTOM]]` e `[[custom|CONSUETUDINE]]` puntano allo
stesso nodo, quindi chi cerca "custom" trova anche la pagina italiana e
viceversa. Tradurre il bersaglio (`[[consuetudine|...]]`) spezzerebbe il link:
quel nodo non esiste.

Corollario: **non si aggiungono né si tolgono wikilink.** Se l'inglese ne ha
tre, l'italiano ne ha tre, sugli stessi punti. Non è compito del traduttore
decidere cosa linkare.

Se l'etichetta coincide col bersaglio (`[[dialectic|dialectic]]`), in italiano
diventa `[[dialectic|dialettica]]` — mai `[[dialettica]]`.

## Corpo

1. **Stessa struttura a blocchi.** Stesso numero di paragrafi, stesso ordine.
   Un paragrafo inglese lungo resta un paragrafo italiano lungo: non si spezza
   per comodità, non si fondono due paragrafi in uno.
2. **H1 tradotto, non rimosso.** `# II.` resta `# II.` (numerazione romana:
   invariata). `# PREFACE.` diventa `# PREFAZIONE.`
3. **Markdown identico.** Corsivi, blockquote, elenchi, interruzioni di riga a
   due spazi: stessa forma della fonte.
4. **Nessun apparato.** Niente note del traduttore, niente `[N.d.T.]`, niente
   parentesi esplicative aggiunte, niente introduzioni. Il sito non pubblica
   apparati editoriali: una nota aggiunta qui è esattamente ciò che il progetto
   esclude.
5. **Registro fedele all'epoca.** Non si modernizza, non si addolcisce, non si
   censura. Seneca stoico suona stoico; Marx polemico suona polemico.
6. **Nomi propri.** Si traducono solo quelli con forma italiana consolidata
   (`Cato` → `Catone`, `Jupiter` → `Giove`, `Caesar` → `Cesare`). Gli altri
   restano invariati.
7. **Terminologia filosofica coerente dentro l'opera.** Lo stesso termine
   tecnico rende sempre con lo stesso traducente lungo tutta l'opera
   (`understanding` → `intelletto`, non a volte `comprensione`).

## Fonte del testo

Si traduce **dal testo dell'atomo di partenza**, nella lingua in cui è (campo
`lang`), verso ciascuna lingua mancante:

- fonte **inglese**: si produce solo l'italiano, traducendo dall'inglese.
- fonte **spagnola / tedesca / francese / latina / greca**: si producono
  entrambi, `.en.md` e `.it.md`, traducendo **ciascuno direttamente
  dall'originale** — mai l'italiano dall'inglese appena fatto. Le due traduzioni
  sono sorelle dello stesso originale, non l'una figlia dell'altra: relayare
  (originale → EN → IT) accumulerebbe le derive di due passaggi.

In tutti i casi la corrispondenza dei blocchi è con l'atomo di partenza: stesso
numero di paragrafi, stesso ordine, stessi wikilink negli stessi punti (vedi
sopra). Non si va a cercare un'altra edizione dell'opera.

## Verifica

```
C:\Users\utente\AppData\Local\Programs\Python\Python312\python.exe scripts/translate/verify.py
```

Controlla, su ogni `.it.md` e `.en.md` del vault: frontmatter agganciato
all'atomo giusto (`lang` coerente col suffisso), conteggio dei blocchi uguale
alla fonte, H1 presente se la fonte ce l'ha, invarianza dei bersagli dei
wikilink rispetto alla fonte, e — per l'italiano — assenza di residui inglesi
evidenti. Esce diverso da zero se qualcosa non torna.
