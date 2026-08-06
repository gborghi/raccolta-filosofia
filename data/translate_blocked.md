# Atomi non traducibili in automatico

Roba che i traduttori-agente non riescono a produrre, da gestire in altro modo.
Ogni voce: opera, lingua-fonte, atomi, motivo, cosa serve.

## Aristotele — Metaphysics (Perseus TEI), greco antico

- **Opera:** `Metaphysics_980a` (Libro I / Alpha)
- **Atomi:** i primi 7 (slice 1-7) — probabilmente l'intera opera, 71 atomi, ha lo stesso problema
- **Fonte:** greco antico politonico (`lang: grc`)
- **Motivo:** l'agente traduttore muore con `400 Output blocked by content filtering policy` — due tentativi indipendenti, stesso errore, allo stadio di OUTPUT della traduzione (legge il greco bene, poi il filtro blocca l'emissione). Non è un problema del testo di partenza né dei wikilink (non ce ne sono): è il filtro contenuti sul canale degli agenti che scatta in modo persistente su questo materiale.
- **Cosa serve:** tradurre EN + IT fuori dal canale-agente. Opzioni: (a) traduzione fatta a mano / da te; (b) una traduzione PD inglese esistente della Metaphysics (Ross, PD) atomizzata in parallelo come fonte EN, e IT tradotto da lì; (c) provare un canale diverso. Il greco resta comunque pubblicato come lingua originale; mancano solo i sibling `.en.md`/`.it.md`.
- **Stato:** BLOCCO CONFERMATO — tre tentativi indipendenti sul canale-agente, tutti `400 Output blocked by content filtering policy`, anche istruendo l'agente a non riprodurre mai il greco. Il filtro scatta ogni volta che il greco politonico e' nel contesto del modello e questo genera output sostanzioso. Non aggirabile col prompt sul canale-agente.
- **Vie residue:** (a) traduzione nel main-thread (canale diverso dal filtro-agente) — 71 atomi densi, oneroso ma possibile a ondate; (b) procurarsi una traduzione inglese PD della Metaphysics (es. McMahon 1857, pubblico dominio) e atomizzarla come fonte EN, poi IT da li' — richiede di far combaciare i blocchi con i 71 atomi greci; (c) canale/tool esterno. Da decidere con l'utente.
