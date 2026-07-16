// Reading-page SPA router.
//
// When preprocess runs with SPA=1 it emits ONE page per work: every atom's body is
// concatenated behind an inline `<span class="atom-split" data-atom data-title
// data-chapter data-kind>` marker (and each atom's optional Italian body behind the
// existing `<span class="qlang-split" data-lang="it">` marker). Quartz renders the
// whole page normally — wikilinks, prose, popovers, translations — so the full text
// is in the HTML (SEO-safe). This script then:
//   1. partitions the rendered article DOM at the markers into per-atom node groups
//      (same DOM-slicing trick the qlang toggle uses), splitting each into EN/IT;
//   2. detaches them and shows ONE atom at a time inside a reading pane, so the live
//      DOM stays small even for a 400-atom novel (render-on-demand);
//   3. deep-links each atom at `#atomId` (history + back/forward + arrow keys);
//   4. builds a chapter/part table of contents and prev/next;
//   5. offers a single work-level EN/IT toggle that governs every atom.
//
// Mounted only on pages that carry a `<div class="atom-reader">` placeholder.

interface Atom {
  id: string
  title: string
  chapter: string
  kind: string
  en: Node[]
  it: Node[]
}

const LANG_KEY = "eng-reader-lang"

// Una voce di "Opere collegate" o "In contrasto" (vedi atom_related in preprocess.mjs).
interface RelatedItem {
  href: string
  title: string
  philosopher?: string
  shared?: number
  pair?: [string, string] // la coppia che si oppone: [posizione dell'atomo, posizione contraria]
}
interface AtomRelated {
  a?: RelatedItem[] // affinita': "Opere collegate"
  c?: RelatedItem[] // opposizione dichiarata (taxonomy `contro`): "In contrasto"
}

// The set of work-shard keys that actually have atom-related data, loaded once from
// static/atom_related/_index.json (emitted by preprocess). Gating shard fetches on
// this avoids a 404 on every reading page that has no shard.
let relatedIndexPromise: Promise<Set<string>> | null = null
function relatedIndex(bp: string): Promise<Set<string>> {
  if (!relatedIndexPromise) {
    relatedIndexPromise = fetch(`${bp}/static/atom_related/_index.json`)
      .then((r) => (r.ok ? (r.json() as Promise<string[]>) : []))
      .then((a) => new Set(a))
      .catch(() => new Set<string>())
  }
  return relatedIndexPromise
}

// A marker (`.atom-split` / `.qlang-split`) is emitted as an inline <span>; the
// markdown renderer wraps a lone inline element in a <p>, so the marker is usually
// NOT a direct child of the article — it sits inside a <p> that contains nothing
// else. Detect both shapes: the bare marker element, or a wrapper whose only element
// child is a marker and which carries no text of its own.
function markerOf(el: HTMLElement): HTMLElement | null {
  if (el.classList && (el.classList.contains("atom-split") || el.classList.contains("qlang-split")))
    return el
  if (el.childElementCount === 1 && !(el.textContent || "").trim()) {
    const c = el.firstElementChild as HTMLElement | null
    if (c && c.classList && (c.classList.contains("atom-split") || c.classList.contains("qlang-split")))
      return c
  }
  return null
}

function partition(
  container: HTMLElement,
  mount: HTMLElement,
): { atoms: Atom[]; markerNodes: Node[] } {
  const atoms: Atom[] = []
  const markerNodes: Node[] = [] // the top-level nodes (bare marker or its wrapping <p>) to detach
  let cur: Atom | null = null
  let lang: "en" | "it" = "en"
  for (const node of Array.from(container.childNodes)) {
    if (node === mount) continue
    if (node.nodeType === Node.ELEMENT_NODE) {
      const marker = markerOf(node as HTMLElement)
      if (marker) {
        markerNodes.push(node)
        if (marker.classList.contains("atom-split")) {
          cur = {
            id: marker.dataset.atom || `atom-${atoms.length}`,
            title: marker.dataset.title || "",
            chapter: marker.dataset.chapter || "",
            kind: marker.dataset.kind || "",
            en: [],
            it: [],
          }
          atoms.push(cur)
          lang = "en"
        } else {
          lang = "it"
        }
        continue
      }
    }
    if (cur) (lang === "en" ? cur.en : cur.it).push(node)
  }
  return { atoms, markerNodes }
}

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  cls?: string,
  html?: string,
): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag)
  if (cls) e.className = cls
  if (html != null) e.innerHTML = html
  return e
}

// The emitted title is the full "Work — Chapter (part N)"; crumb/TOC only want the
// chapter/part portion (the work title is already in the page header + breadcrumb).
function chapterOf(t: string): string {
  return t.replace(/^.*—\s*/, "")
}
// TOC leaf under a chapter group: strip the repeated chapter name so a part reads
// just "Parte 3" instead of "II The Maniac (part 3)".
function leafLabel(a: Atom): string {
  let s = chapterOf(a.title)
  if (a.chapter && s.startsWith(a.chapter)) {
    s = s.slice(a.chapter.length).replace(/^[\s—–-]+/, "").trim() || s
  }
  return s.replace(/^\((?:part|parte)\s*(\d+)\)$/i, "Parte $1")
}

function build(reader: HTMLElement) {
  if (reader.dataset.mounted) return
  reader.dataset.mounted = "1"
  const container = reader.parentElement
  if (!container) return

  const { atoms, markerNodes } = partition(container, reader)
  if (!atoms.length) return
  const anyIt = atoms.some((a) => a.it.length > 0)

  // detach every atom's nodes + the marker nodes (bare span or its wrapping <p>) so
  // no empty marker boxes linger in the flow
  for (const m of markerNodes) m.parentNode?.removeChild(m)
  for (const a of atoms) for (const n of [...a.en, ...a.it]) n.parentNode?.removeChild(n)

  const order = atoms.map((a) => a.id)
  const byId = new Map(atoms.map((a) => [a.id, a]))
  let lang: "en" | "it" =
    anyIt && localStorage.getItem(LANG_KEY) === "it" ? "it" : "en"

  // "Opere collegate" / "In contrasto" per atomo: chiave "<workSlug>#<atomId>", la
  // stessa che preprocess emette e che l'hash della pagina risolve. Caricato async; al
  // suo arrivo scatta un re-render. Lo possiede il router (non relatedWorks.inline.ts)
  // perche' il pannello di lettura viene sostituito a ogni cambio di atomo.
  const workSlug = reader.dataset.work || ""
  const BP = (document.body && (document.body as HTMLElement).dataset.basepath) || ""
  let relatedData: Record<string, AtomRelated> | null = null
  // Per-work shard (few KB) instead of one index for the whole corpus. Reading pages
  // whose work has no shard must not fetch one, so gate on the tiny manifest
  // (relatedIndex) — otherwise every one of them logs a 404 for a missing file.
  const shardKey = workSlug.replace(/\//g, "__")
  relatedIndex(BP).then((idx) => {
    if (!idx.has(shardKey)) return // no shard for this work → skip the fetch (no 404)
    fetch(`${BP}/static/atom_related/${shardKey}.json`)
      .then((r) => (r.ok ? r.json() : {}))
      .then((d) => {
        relatedData = d
        render(shownId)
      })
      .catch(() => {})
  })

  // ---- reader chrome ----
  const bar = el("div", "ar-bar")
  // The global Explorer/search left-sidebar toggle is owned site-wide by
  // sidebarToggle.inline.ts (fixed ☰/✕). The reader only supplies its own chapter-TOC
  // toggle below.
  const tocBtn = el("button", "ar-tocbtn", "&#9776;")
  tocBtn.setAttribute("aria-label", "Indice")
  const crumb = el("div", "ar-crumb")
  const spacer = el("div", "ar-spacer")
  const langWrap = el("div", "ar-lang")
  const enBtn = el("button", "", "EN")
  const itBtn = el("button", "", "IT")
  enBtn.dataset.l = "en"
  itBtn.dataset.l = "it"
  langWrap.append(enBtn, itBtn)
  const pager = el("div", "ar-pager")
  const prevBtn = el("button", "ar-prev", "&#8249;")
  const nextBtn = el("button", "ar-next", "&#8250;")
  prevBtn.setAttribute("aria-label", "Precedente")
  nextBtn.setAttribute("aria-label", "Successivo")
  pager.append(prevBtn, nextBtn)
  bar.append(tocBtn, crumb, spacer)
  if (anyIt) bar.append(langWrap)
  bar.append(pager)

  const shell = el("div", "ar-shell")
  const toc = el("nav", "ar-toc")
  toc.setAttribute("aria-label", "Indice")
  const pane = el("article", "ar-pane")
  shell.append(toc, pane)
  const relatedEl = el("aside", "ar-related")

  reader.replaceChildren(bar, shell, relatedEl)

  // ---- table of contents (grouped by chapter) ----
  const tocList = el("ul", "ar-toc-list")
  let curChap: string | null = null
  let curUl: HTMLUListElement | null = null
  for (const a of atoms) {
    const label = a.kind === "intro" ? a.title || "Inizio" : a.title
    if (a.kind === "intro" || !a.chapter) {
      const li = el("li", "ar-toc-top")
      const link = el("a", "ar-toc-link", label)
      link.href = `#${a.id}`
      link.dataset.id = a.id
      li.append(link)
      tocList.append(li)
      curChap = null
      curUl = null
      continue
    }
    if (a.chapter !== curChap) {
      curChap = a.chapter
      const li = el("li", "ar-toc-chap")
      li.append(el("span", "ar-toc-chaplabel", a.chapter))
      curUl = el("ul")
      li.append(curUl)
      tocList.append(li)
    }
    const li = el("li")
    const link = el("a", "ar-toc-link", leafLabel(a) || a.id)
    link.href = `#${a.id}`
    link.dataset.id = a.id
    li.append(link)
    curUl?.append(li)
  }
  toc.append(tocList)

  // ---- rendering ----
  let shownId = order[0] // the resolved leaf currently displayed (drives prev/next)
  function idx(id: string) {
    return order.indexOf(id)
  }
  function applyLangButtons() {
    enBtn.classList.toggle("active", lang === "en")
    itBtn.classList.toggle("active", lang === "it")
  }
  // Un blocco di rinvii ad altre OPERE (mai a un atomo: il rinvio e' all'opera, che si
  // apre sulla sua prima pagina). L'opera dell'atomo corrente non c'e' mai — la esclude
  // preprocess, sia nell'affinita' sia nel contrasto.
  function section(title: string, items: RelatedItem[], cls: string): HTMLElement {
    const wrap = el("section", cls)
    wrap.append(el("h2", undefined, title))
    const ul = document.createElement("ul")
    for (const it of items) {
      const li = document.createElement("li")
      li.className = "rw-work"
      const link = document.createElement("a")
      link.href = `${BP}/${it.href}`
      link.textContent = it.title || it.href
      li.append(link)
      if (it.philosopher) {
        const p = document.createElement("span")
        p.className = "rw-author"
        p.textContent = ` — ${it.philosopher}`
        li.append(p)
      }
      // Quale coppia si oppone, in chiaro: senza, "In contrasto" e' un elenco di
      // titoli da prendere sulla fiducia. Gli id sono quelli canonici del vocabolario
      // (language-agnostic), gli stessi che il lettore ritrova nelle pagine dei nodi.
      if (it.pair) {
        const d = document.createElement("div")
        d.className = "rw-pair"
        d.textContent = `${it.pair[0]} ↔ ${it.pair[1]}`
        li.append(d)
      }
      ul.append(li)
    }
    wrap.append(ul)
    return wrap
  }

  function render(id: string) {
    const a = byId.get(id) || atoms[0]
    shownId = a.id
    let nodes = lang === "it" && a.it.length ? a.it : a.en
    pane.replaceChildren(...nodes.map((n) => n))
    if (lang === "it" && !a.it.length && anyIt) {
      pane.append(el("p", "ar-notr", "— traduzione non disponibile per questa sezione —"))
    }
    // crumb + counter: chapter in bold, then the leaf only when it adds info
    const pos = idx(a.id) + 1
    const leaf = a.kind === "intro" ? a.title || "Inizio" : leafLabel(a)
    const showLeaf = !a.chapter || leaf !== a.chapter
    crumb.innerHTML =
      (a.chapter ? `<b>${a.chapter}</b>` : "") +
      (a.chapter && showLeaf ? " &middot; " : "") +
      (showLeaf ? leaf : "") +
      ` <span class="ar-count">${pos} / ${order.length}</span>`
    // toc active
    toc.querySelectorAll(".ar-toc-link").forEach((l) =>
      l.classList.toggle("active", (l as HTMLElement).dataset.id === a.id),
    )
    const active = toc.querySelector(".ar-toc-link.active") as HTMLElement | null
    active?.scrollIntoView({ block: "nearest" })
    // "Opere collegate" / "In contrasto" per QUESTO atomo. Un atomo di pura narrazione
    // non nomina nessun nodo del vocabolario e quindi non ha una chiave: sotto non
    // compare niente, ed e' la risposta giusta — non un buco da riempire.
    relatedEl.replaceChildren()
    relatedEl.className = "ar-related"
    const rel = relatedData && relatedData[`${workSlug}#${a.id}`]
    if (rel && ((rel.a && rel.a.length) || (rel.c && rel.c.length))) {
      relatedEl.className = "ar-related related-works"
      if (rel.a?.length) relatedEl.append(section("Opere collegate", rel.a, "rw-affinity"))
      if (rel.c?.length) relatedEl.append(section("In contrasto", rel.c, "rw-contrast"))
    }
    const i = idx(a.id)
    prevBtn.disabled = i <= 0
    nextBtn.disabled = i >= order.length - 1
    pane.scrollTo?.(0, 0)
    window.scrollTo(0, 0)
  }
  function go(id: string, push: boolean) {
    if (!byId.has(id)) {
      // a chapter/aggregate id (e.g. #chapter_01 from a related card, a wikilink to a
      // whole chapter, or the 404 redirect): land on that chapter's first leaf.
      id = order.find((o) => o.startsWith(`${id}--`)) || order[0]
    }
    render(id)
    if (push && location.hash.slice(1) !== id) history.pushState(null, "", `#${id}`)
    shell.classList.remove("toc-open")
  }
  function current(): string {
    // raw hash — go() resolves chapter/aggregate ids to a leaf.
    return decodeURIComponent(location.hash.slice(1)) || order[0]
  }

  enBtn.onclick = () => {
    lang = "en"
    localStorage.setItem(LANG_KEY, "en")
    applyLangButtons()
    render(shownId)
  }
  itBtn.onclick = () => {
    lang = "it"
    localStorage.setItem(LANG_KEY, "it")
    applyLangButtons()
    render(shownId)
  }
  prevBtn.onclick = () => {
    const i = idx(shownId)
    if (i > 0) go(order[i - 1], true)
  }
  nextBtn.onclick = () => {
    const i = idx(shownId)
    if (i < order.length - 1) go(order[i + 1], true)
  }
  tocBtn.onclick = () => shell.classList.toggle("toc-open")
  reader.addEventListener("click", (e) => {
    const a = (e.target as HTMLElement).closest?.('a[href^="#"]') as HTMLAnchorElement | null
    if (!a || !reader.contains(a)) return
    const id = decodeURIComponent(a.getAttribute("href")!.slice(1))
    if (byId.has(id)) {
      e.preventDefault()
      go(id, true)
    }
  })
  window.addEventListener("popstate", () => go(current(), false))
  document.addEventListener("keydown", (e) => {
    if ((e.target as HTMLElement).matches?.("input,textarea")) return
    if (e.key === "ArrowRight") {
      const i = idx(shownId)
      if (i < order.length - 1) go(order[i + 1], true)
    } else if (e.key === "ArrowLeft") {
      const i = idx(shownId)
      if (i > 0) go(order[i - 1], true)
    }
  })

  applyLangButtons()
  go(current(), false)
}

function init() {
  const readers = document.querySelectorAll<HTMLElement>("div.atom-reader")
  // reading pages collapse the global left sidebar (see build()); leaving one must
  // restore normal layout for the next SPA-navigated page. The ☰/✕ chrome that opens
  // and closes that sidebar is owned globally by sidebarToggle.inline.ts.
  document.body.classList.toggle("reading-page", readers.length > 0)
  if (!readers.length) document.body.classList.remove("left-open")
  readers.forEach((r) => build(r))
}

document.addEventListener("nav", init)
init()

export {}
