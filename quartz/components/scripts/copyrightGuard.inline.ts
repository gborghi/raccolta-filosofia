// Copyright guard for in-copyright authors.
//
// WHAT THIS DOES AND DOES NOT DO — read before trusting it.
//
// Nothing is withheld from the build: the full text ships in the page and in the
// search index, and this script only hides it in the browser. View-source, curl,
// JS disabled or the search index all still reach it. This is a NOTICE, not an
// access control. It is a deliberate choice, matching the sibling English site.
// If a text must genuinely not ship, it has to be dropped in preprocess.mjs —
// the emitter is the only real gate.
//
// Every check is DATE-DRIVEN, so the moment the term lapses the text reappears by
// itself, with no redeploy and no code change.
//
// The term is per-author because it is NOT the same everywhere, and getting it
// from a single hardcoded constant is how you end up with an inert guard:
//   Ortega y Gasset — died 18 Oct 1955, Spain. The EU default of 70 years would
//   put him in the public domain in 2026 (i.e. now — the guard would be a no-op).
//   But Spain's transitional rule (TRLPI, disp. trans. 4ª) keeps authors who died
//   before 7 Dec 1987 under a term of 80 years. Spain is the work's country of
//   origin, and 80 is the prudent read: PD on 1 Jan 2036.
const GUARDED: Record<string, { died: string; term: number; name: string }> = {
  ortega: { died: "1955-10-18", term: 80, name: "José Ortega y Gasset" },
}

// 1 Jan of (deathYear + term + 1): the term runs to the END of the Nth calendar
// year after death, so the work is free on the first day of the year after that.
function pdDate(a: { died: string; term: number }): Date {
  return new Date(pdYear(a), 0, 1)
}
function pdYear(a: { died: string; term: number }): number {
  return parseInt(a.died.slice(0, 4), 10) + a.term + 1
}

function activeAuthors(): string[] {
  const now = new Date()
  return Object.keys(GUARDED).filter((a) => now < pdDate(GUARDED[a]))
}

function notice(author: string): HTMLElement {
  const entry = GUARDED[author]
  const name = entry.name
  const year = pdYear(entry)
  const el = document.createElement("div")
  el.className = "cr-guard"
  el.setAttribute("role", "note")
  el.innerHTML =
    `<div class="cr-guard-badge">©</div>` +
    `<div class="cr-guard-body">` +
    `<p class="cr-guard-en"><strong>Text under copyright.</strong> Works by ${name} remain ` +
    `protected until ${year}. The full text is withheld here until it enters the public ` +
    `domain, when it will appear automatically.</p>` +
    `<p class="cr-guard-it"><strong>Testo protetto da copyright.</strong> Le opere di ` +
    `${name} sono tutelate fino al ${year}. Il testo integrale comparirà ` +
    `automaticamente alla scadenza del diritto d'autore.</p>` +
    `</div>`
  return el
}

// Reading page (/testi/<philosopher>/<work>): hide the text, keep the abstract.
//
// This is where the English original does NOT port over. There, a work note and its
// text live on separate pages, so the guard hides one and leaves the other. Here the
// work page IS the SPA reading page: the atoms are inline behind the `.atom-reader`
// mount. Hiding "everything" would leave a blank page, so the abstract — which we
// wrote ourselves and which is therefore ours to publish — is what stays.
function guardReadingPage(article: HTMLElement, author: string): void {
  if (article.querySelector(":scope > .cr-guard")) return
  let anchor: Element | null = null
  for (const child of Array.from(article.children)) {
    // The abstract callout and the page title survive; the text does not.
    if (child.matches(".callout, h1")) {
      anchor = child
      continue
    }
    ;(child as HTMLElement).style.display = "none"
  }
  const note = notice(author)
  if (anchor && anchor.nextSibling) article.insertBefore(note, anchor.nextSibling)
  else article.insertBefore(note, article.firstChild)
}

let observer: MutationObserver | null = null

function apply(): void {
  observer?.disconnect()
  observer = null

  const active = activeAuthors()
  if (!active.length) return

  const slug = (document.body.dataset.slug || "").toLowerCase()
  const article =
    (document.querySelector("article") as HTMLElement | null) ||
    (document.querySelector(".center") as HTMLElement | null)
  if (!article) return

  const author = active.find((a) => slug.startsWith(`testi/${a}/`))
  if (!author) return

  guardReadingPage(article, author)

  // atomRouter renders the reader asynchronously and replaces the pane on every
  // atom change: a one-shot pass would be undone by the first render. Links to the
  // work stay visible on purpose — the reader is meant to land here and find the
  // abstract plus the notice, rather than find nothing at all.
  let queued = false
  observer = new MutationObserver(() => {
    if (queued) return
    queued = true
    requestAnimationFrame(() => {
      queued = false
      const reader = article.querySelector(".atom-reader") as HTMLElement | null
      if (reader) reader.style.display = "none"
    })
  })
  observer.observe(article, { childList: true, subtree: true })
}

document.addEventListener("nav", apply)
apply()
