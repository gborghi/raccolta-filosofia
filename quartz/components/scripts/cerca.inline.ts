// Faceted multi-select search for the /cerca page. Loads index.json and lets the
// user combine tags across facets (Author, Cluster, Topos, Archetype, Motif,
// Theme/Concept, Form, Historical Reference, Setting, Character), rendering
// matches into a sortable, paginated table. Two match modes:
//   ANY (default): OR within a facet group, AND across groups (faceted search)
//   ANYTAG: pure OR — a work matches if it carries any selected tag (OR within, OR across).

import { esc, slugPrefix, loadKw, kwCached, makeModeToggle } from "./qtable"

const KW_FILE = "works_kw.json"

// Record opera come da index.json (preprocess.mjs). Le facce sono la tassonomia
// Philosophy — NON i campi letterari di ../English (topos/archetype/motif/
// character), che qui non esistono e davano facce vuote + colonne "undefined".
interface Work {
  href: string
  readHref?: string
  title: string
  author: string
  lang: string
  words: number
  atoms: number
  axes: string[]
  positions: string[]
  concepts: string[]
  arguments: string[]
  figures: string[]
  forms: string[]
  schools: string[]
}

interface Facet {
  key: keyof Work
  label: string
  multi?: boolean
}

const FACETS: Facet[] = [
  { key: "author", label: "Autore" },
  { key: "lang", label: "Lingua" },
  { key: "axes", label: "Assi", multi: true },
  { key: "positions", label: "Posizioni", multi: true },
  { key: "concepts", label: "Concetti", multi: true },
  { key: "arguments", label: "Argomenti", multi: true },
  { key: "figures", label: "Figure", multi: true },
  { key: "forms", label: "Forme", multi: true },
  { key: "schools", label: "Scuole", multi: true },
]

const PER_PAGE_OPTS = [25, 50, 100, 250, 0] // 0 = All
const LS_KEY = "englit-qtable-perpage"
function getPerPage(): number {
  const raw = localStorage.getItem(LS_KEY)
  if (raw == null) return 50
  const v = Number(raw)
  return PER_PAGE_OPTS.includes(v) ? v : 50
}

function pretty(v: string): string {
  const s = v.replace(/_/g, " ")
  return s.charAt(0).toUpperCase() + s.slice(1)
}

async function init() {
  const root = document.getElementById("cerca")
  if (!root || root.dataset.rendered) return
  root.dataset.rendered = "1"

  const prefix = slugPrefix()
  let data: Work[]
  try {
    data = await (await fetch(prefix + "static/index.json")).json()
  } catch {
    root.textContent = "Could not load the works index."
    return
  }

  // selected tags as "facetKey::value"
  const selected = new Set<string>()
  // ANY    = OR within a facet group, AND across groups (faceted default).
  // ANYTAG = pure OR: a work matches if it carries any selected tag (OR within, OR across).
  let mode: "ANY" | "ANYTAG" = "ANY"

  // Deep-link: the home author cards stash an "author::Name" token in
  // sessionStorage (Quartz mangles query/hash params in hrefs, so JS is used).
  // Also honour an explicit ?author= / ?cluster= query string if present.
  try {
    const pre = sessionStorage.getItem("cercaPreselect")
    if (pre) {
      selected.add(pre)
      sessionStorage.removeItem("cercaPreselect")
    }
  } catch {}
  const params = new URLSearchParams(location.search.replace(/^\?/, ""))
  const qpAuthor = params.get("author")
  if (qpAuthor) selected.add(`author::${decodeURIComponent(qpAuthor)}`)

  const facetValues: { facet: Facet; values: [string, number][] }[] = FACETS.map((facet) => {
    const counts = new Map<string, number>()
    for (const w of data) {
      const raw = w[facet.key] as unknown
      const vals = facet.multi
        ? ((raw as string[]) || [])
        : raw === "" || raw == null
          ? []
          : [String(raw)]
      for (const v of vals) counts.set(v, (counts.get(v) || 0) + 1)
    }
    const values = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    return { facet, values }
  })

  const hasValue = (w: Work, key: string, val: string): boolean => {
    const facet = FACETS.find((f) => f.key === key)!
    return facet.multi
      ? ((w[facet.key] as unknown as string[]) || []).includes(val)
      : String(w[facet.key]) === val
  }

  function matches(w: Work): boolean {
    if (selected.size === 0) return false
    if (mode === "ANYTAG") {
      // Pure OR: the work matches if it carries ANY selected tag (OR within AND across groups).
      for (const token of selected) {
        const idx = token.indexOf("::")
        if (hasValue(w, token.slice(0, idx), token.slice(idx + 2))) return true
      }
      return false
    }
    // ANY: group the selected tokens by facet, OR within a group and AND across
    // groups — a work must hit at least one selected value in EVERY facet that
    // has a selection. (e.g. "Keats OR Shelley" AND "Topos=Sea OR Topos=Death")
    const byFacet = new Map<string, string[]>()
    for (const token of selected) {
      const idx = token.indexOf("::")
      const key = token.slice(0, idx)
      const val = token.slice(idx + 2)
      const arr = byFacet.get(key)
      if (arr) arr.push(val)
      else byFacet.set(key, [val])
    }
    for (const [key, vals] of byFacet) {
      if (!vals.some((val) => hasValue(w, key, val))) return false // OR within facet; AND across facets
    }
    return true
  }

  const controls = document.createElement("div")
  controls.className = "cerca-controls"
  const facetsBox = document.createElement("div")
  facetsBox.className = "cerca-facets"
  const selectedBar = document.createElement("div")
  selectedBar.className = "cerca-selected"
  const resultsBox = document.createElement("div")
  resultsBox.className = "cerca-results"
  root.replaceChildren(controls, facetsBox, selectedBar, resultsBox)

  // ---- search & pagination controls ----
  let filter = ""
  let page = 1
  let perPage = getPerPage()
  let searchMode: "table" | "content" = "table"

  const hint = document.createElement("p")
  hint.className = "cerca-hint"
  hint.textContent =
    "Seleziona uno o più tag qui sopra, o scrivi nella casella di ricerca, per vedere le opere corrispondenti."

  const search = document.createElement("input")
  search.type = "search"
  search.className = "qtable-search"
  const setPlaceholder = () => {
    search.placeholder =
      searchMode === "content" ? "Cerca nel testo completo delle opere…" : "Filtra i risultati (titolo/autore/lingua)…"
  }
  setPlaceholder()
  search.addEventListener("input", () => {
    filter = search.value
    page = 1
    renderResults()
  })

  const modeBtn = makeModeToggle({
    label: () => (searchMode === "content" ? "Search: full content" : "Search: title/author"),
    isContent: () => searchMode === "content",
    onToggle: () => {
      searchMode = searchMode === "table" ? "content" : "table"
      setPlaceholder()
      page = 1
    },
    needKw: () => searchMode === "content" && !kwCached(KW_FILE),
    loadKw: () => loadKw(prefix, KW_FILE),
    rerender: () => renderResults(),
  })

  const searchRow = document.createElement("div")
  searchRow.className = "qtable-searchrow"
  searchRow.append(search, modeBtn)

  const count = document.createElement("div")
  count.className = "cerca-count"

  const perPageSel = document.createElement("select")
  perPageSel.className = "paged-perpage"
  for (const n of PER_PAGE_OPTS) {
    const o = document.createElement("option")
    o.value = String(n)
    o.textContent = n === 0 ? "All" : String(n)
    if (n === perPage) o.selected = true
    perPageSel.appendChild(o)
  }
  perPageSel.addEventListener("change", () => {
    perPage = Number(perPageSel.value)
    localStorage.setItem(LS_KEY, String(perPage))
    page = 1
    renderResults()
  })
  const perPageLbl = document.createElement("label")
  perPageLbl.className = "paged-perpage-label"
  perPageLbl.append("show ", perPageSel, " per page")

  const resControls = document.createElement("div")
  resControls.className = "qtable-controls"
  resControls.append(count, perPageLbl)

  const table = document.createElement("table")
  table.className = "lt-table"

  const pager = document.createElement("div")
  pager.className = "qtable-pager"
  pager.addEventListener("click", (e) => {
    const t = (e.target as HTMLElement).closest("button[data-p]") as HTMLElement | null
    if (!t) return
    page = Number(t.dataset.p)
    renderResults()
    resultsBox.scrollIntoView({ block: "start", behavior: "smooth" })
  })

  resultsBox.replaceChildren(hint, searchRow, resControls, table, pager)
  // ------------------------------------

  const toggle = document.createElement("button")
  toggle.className = "cerca-toggle"
  function syncToggle() {
    toggle.textContent =
      mode === "ANY"
        ? "Match: ANY in group (OR within a group, AND across groups)"
        : "Match: ANY selected tag (OR within, OR across)"
    toggle.setAttribute("aria-pressed", String(mode === "ANYTAG"))
  }
  toggle.addEventListener("click", () => {
    mode = mode === "ANY" ? "ANYTAG" : "ANY"
    syncToggle()
    page = 1
    render()
  })
  syncToggle()
  controls.appendChild(toggle)

  for (const { facet, values } of facetValues) {
    const sec = document.createElement("details")
    sec.className = "cerca-facet"
    const sum = document.createElement("summary")
    sum.textContent = `${facet.label} (${values.length})`
    sec.appendChild(sum)
    const chips = document.createElement("div")
    chips.className = "cerca-chips"
    for (const [val, c] of values) {
      const token = `${facet.key}::${val}`
      const chip = document.createElement("button")
      chip.className = "cerca-chip"
      chip.dataset.token = token
      chip.innerHTML = `${esc(facet.multi ? pretty(val) : val)} <span class="cerca-n">${c}</span>`
      chip.addEventListener("click", () => {
        if (selected.has(token)) selected.delete(token)
        else selected.add(token)
        page = 1
        render()
      })
      chips.appendChild(chip)
    }
    sec.appendChild(chips)
    facetsBox.appendChild(sec)
  }

  let sortKey: keyof Work = "title"
  let sortDir = 1
  function renderResults() {
    const q = filter.trim().toLowerCase()
    // Show results when a tag is selected OR a free-text query is typed, so the
    // content/title search works on the whole corpus without picking a tag first
    // (the search box + mode toggle stay visible at all times).
    const active = selected.size > 0 || q !== ""
    hint.style.display = active ? "none" : ""
    resControls.style.display = active ? "" : "none"
    table.style.display = active ? "" : "none"
    if (!active) {
      pager.innerHTML = ""
      count.innerHTML = ""
      return
    }

    let rows = selected.size > 0 ? data.filter(matches) : data.slice()
    if (q) {
      const terms = q.split(/\s+/).filter(Boolean)
      rows = rows.filter((r) => {
        if (searchMode === "content") {
          const kw = kwCached(KW_FILE)?.[r.href]
          if (!kw) return false
          // token-AND: every query word must appear in the work's keyword text
          // (works_kw.json is a deduped word bag, so a whole-string match fails).
          return terms.every((t) => kw.includes(t))
        }
        return terms.every(
          (t) =>
            String(r.title).toLowerCase().includes(t) ||
            String(r.author).toLowerCase().includes(t) ||
            String(r.lang).toLowerCase().includes(t),
        )
      })
    }

    rows.sort((a, b) => {
      let av: any = a[sortKey]
      let bv: any = b[sortKey]
      if (sortKey === "words" || sortKey === "atoms") {
        av = Number(av)
        bv = Number(bv)
      } else {
        av = String(av).toLowerCase()
        bv = String(bv).toLowerCase()
      }
      if (av < bv) return -sortDir
      if (av > bv) return sortDir
      return a.title.toLowerCase() < b.title.toLowerCase() ? -1 : 1
    })

    const total = rows.length
    const pages = perPage === 0 ? 1 : Math.max(1, Math.ceil(total / perPage))
    if (page > pages) page = pages
    if (page < 1) page = 1
    const start = perPage === 0 ? 0 : (page - 1) * perPage
    const pageRows = perPage === 0 ? rows : rows.slice(start, start + perPage)

    count.innerHTML =
      pages > 1
        ? `<strong>${total}</strong> opere &mdash; ${start + 1}&ndash;${start + pageRows.length} (pagina ${page}/${pages})`
        : `<strong>${total}</strong> opere`

    const cols: [keyof Work, string, boolean][] = [
      ["title", "Titolo", false],
      ["author", "Autore", false],
      ["lang", "Lingua", false],
      ["words", "Parole", true],
    ]
    const head =
      "<thead><tr>" +
      cols
        .map(
          ([k, l, num]) =>
            `<th data-k="${k}" class="lt-th${num ? " lt-num" : ""}${sortKey === k ? " sorted-" + (sortDir > 0 ? "asc" : "desc") : ""}">${l}</th>`,
        )
        .join("") +
      "</tr></thead>"
    const body =
      "<tbody>" +
      pageRows
        .map(
          (r) =>
            `<tr><td><a href="${prefix}${esc(r.readHref || r.href)}">${esc(r.title)}</a></td>` +
            `<td>${esc(r.author)}</td><td class="lt-lang">${esc(r.lang)}</td><td class="lt-num">${esc(r.words)}</td></tr>`,
        )
        .join("") +
      "</tbody>"

    table.innerHTML = head + body
    table.querySelectorAll<HTMLElement>("th.lt-th").forEach((th) =>
      th.addEventListener("click", () => {
        const k = th.dataset.k as keyof Work
        if (sortKey === k) sortDir *= -1
        else {
          sortKey = k
          sortDir = k === "words" || k === "atoms" ? -1 : 1
        }
        page = 1
        renderResults()
      }),
    )

    // windowed numbered pager (same style as the in-body tables)
    if (pages <= 1) {
      pager.innerHTML = ""
    } else {
      const btn = (label: string, target: number, disabled: boolean, cur = false) =>
        `<button class="paged-btn${cur ? " current" : ""}" data-p="${target}" ${disabled ? "disabled" : ""}>${label}</button>`
      const nums: string[] = []
      const win = 2
      const lo = Math.max(1, page - win)
      const hi = Math.min(pages, page + win)
      if (lo > 1) {
        nums.push(btn("1", 1, false))
        if (lo > 2) nums.push(`<span class="paged-ellip">…</span>`)
      }
      for (let i = lo; i <= hi; i++) nums.push(btn(String(i), i, false, i === page))
      if (hi < pages) {
        if (hi < pages - 1) nums.push(`<span class="paged-ellip">…</span>`)
        nums.push(btn(String(pages), pages, false))
      }
      pager.innerHTML =
        btn("‹ Prev", page - 1, page === 1) + nums.join("") + btn("Next ›", page + 1, page >= pages)
    }
  }

  function renderSelected() {
    if (selected.size === 0) {
      selectedBar.innerHTML = ""
      return
    }
    selectedBar.innerHTML =
      `<span class="cerca-sel-label">Active tags:</span> ` +
      [...selected]
        .map((token) => {
          const idx = token.indexOf("::")
          const key = token.slice(0, idx)
          const val = token.slice(idx + 2)
          const f = FACETS.find((x) => x.key === key)!
          return `<button class="cerca-chip active" data-token="${esc(token)}">${esc(f.label)}: ${esc(f.multi ? pretty(val) : val)} ✕</button>`
        })
        .join("") +
      ` <button class="cerca-clear">Clear all</button>`
    selectedBar.querySelectorAll<HTMLElement>(".cerca-chip.active").forEach((b) =>
      b.addEventListener("click", () => {
        selected.delete(b.dataset.token!)
        page = 1
        render()
      }),
    )
    selectedBar.querySelector(".cerca-clear")?.addEventListener("click", () => {
      selected.clear()
      page = 1
      render()
    })
  }

  function syncChipStates() {
    facetsBox.querySelectorAll<HTMLElement>(".cerca-chip").forEach((c) => {
      c.classList.toggle("active", selected.has(c.dataset.token!))
    })
  }

  function render() {
    syncChipStates()
    renderSelected()
    renderResults()
  }

  render()
}

document.addEventListener("nav", () => {
  init()
})
init()

export {}
