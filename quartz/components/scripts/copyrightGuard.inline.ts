// Copyright guard for in-copyright authors.
//
// Nothing is deleted: the full texts and translations stay in the pages and in the
// search index. While an author is still under copyright we (a) hide the text itself
// on its page behind a copyright notice, and (b) hide navigation links that point to
// those text pages. Every check is DATE-DRIVEN against the public-domain year below,
// so the moment copyright lapses the texts and links reappear automatically with no
// redeploy.
//
// Each author's EXACT death date. Under the UK/EU term (CDPA 1988 s.12 /
// Directive 2006/116) copyright runs "to the end of the 70th calendar year after
// the author dies", so a work enters the public domain on 1 January of
// (yearOfDeath + 71). We store the death date and derive that instant, so the years
// are auditable against the death date rather than hand-entered.
//   T. S. Eliot        — died 4 Jan 1965  → PD 1 Jan 2036
//   Dorothy L. Sayers  — died 17 Dec 1957 → PD 1 Jan 2028
const GUARDED: Record<string, { died: string; name: string }> = {
  eliot: { died: "1965-01-04", name: "T. S. Eliot" },
  sayers: { died: "1957-12-17", name: "Dorothy L. Sayers" },
}

// 1 Jan of (deathYear + 71): the exact moment the work is public domain.
function pdDate(died: string): Date {
  return new Date(parseInt(died.slice(0, 4), 10) + 71, 0, 1)
}
function pdYear(died: string): number {
  return parseInt(died.slice(0, 4), 10) + 71
}

// Headings on a work note whose section body reproduces (or links to) the text.
const TEXT_HEADINGS = /testo integrale|full text|testo \/ text|parti \/ parts|capitoli \/ chapters/i

function activeAuthors(): string[] {
  const now = new Date()
  return Object.keys(GUARDED).filter((a) => now < pdDate(GUARDED[a].died))
}

function notice(author: string): HTMLElement {
  const { name, died } = GUARDED[author]
  const year = pdYear(died)
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

// Hide a heading element and every following sibling up to (not including) the next
// heading of level H1/H2. Returns the elements hidden (so we can restore on expiry —
// though in practice a page load past the PD year simply never hides them).
function hideSection(heading: HTMLElement): void {
  const els: HTMLElement[] = [heading]
  let sib = heading.nextElementSibling
  while (sib && !/^H[12]$/.test(sib.tagName)) {
    els.push(sib as HTMLElement)
    sib = sib.nextElementSibling
  }
  for (const e of els) e.style.display = "none"
}

// Work note (e.g. /works/gerontion-(eliot)): hide the text-bearing sections, keep the
// metadata (byline, abstract, connections). Drop one copyright notice in their place.
function guardWorkNote(article: HTMLElement, author: string): void {
  if (article.querySelector(":scope > .cr-guard")) return
  const heads = Array.from(article.querySelectorAll("h1, h2")) as HTMLElement[]
  let first: HTMLElement | null = null
  for (const h of heads) {
    if (TEXT_HEADINGS.test(h.textContent || "")) {
      if (!first) first = h
      hideSection(h)
    }
  }
  if (first) article.insertBefore(notice(author), first)
}

// Full-text page (/testi/<author>/...): hide the text, keep the breadcrumb / prev-next
// nav so the reader can still move around. Drop the notice where the text was.
function guardTextPage(article: HTMLElement, author: string): void {
  if (article.querySelector(":scope > .cr-guard")) return
  let anchor: Element | null = null
  for (const child of Array.from(article.children)) {
    if (child.matches("nav.excerpt-nav")) {
      anchor = child
      continue
    }
    ;(child as HTMLElement).style.display = "none"
  }
  const note = notice(author)
  if (anchor && anchor.nextSibling) article.insertBefore(note, anchor.nextSibling)
  else article.appendChild(note)
}

// Hide navigation links that point to a guarded /testi/<author>/ text page (brani
// table rows, direct links, …). Hide the enclosing <li>/<tr> when there is one so we
// don't leave an empty bullet or table cell; otherwise neutralise the anchor.
function hideGuardedLinks(root: Document | HTMLElement, rx: RegExp): void {
  root.querySelectorAll("a[href]").forEach((a) => {
    if (!rx.test(a.getAttribute("href") || "")) return
    const box = (a.closest("li, tr") as HTMLElement) || (a as HTMLElement)
    box.style.display = "none"
    box.classList.add("cr-link-hidden")
  })
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

  // 1) guard the page that carries this author's text
  if (article) {
    for (const a of active) {
      if (slug.startsWith(`testi/${a}/`)) {
        guardTextPage(article, a)
        break
      }
      if (slug.endsWith(`(${a})`)) {
        guardWorkNote(article, a)
        break
      }
    }
  }

  // 2) hide links to any guarded text page, wherever they appear (incl. the
  //    client-rendered brani table — re-run on mutations until it settles)
  const rx = new RegExp(`(^|/)testi/(${active.join("|")})/`)
  hideGuardedLinks(document, rx)
  if (article) {
    let queued = false
    observer = new MutationObserver(() => {
      if (queued) return
      queued = true
      requestAnimationFrame(() => {
        queued = false
        hideGuardedLinks(document, rx)
      })
    })
    observer.observe(article, { childList: true, subtree: true })
  }
}

document.addEventListener("nav", apply)
