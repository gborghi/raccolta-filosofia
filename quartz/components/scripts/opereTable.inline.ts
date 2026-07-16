// Renders the static index.json into a sortable, paginated, text-filterable table
// of literary works. Powers the #opere-table div on the Works page, and also any
// #opere-table[data-author] / [data-cluster] scoped variants.

import {
  esc,
  slugPrefix,
  noArticle,
  loadKw,
  kwCached,
  makeModeToggle,
  makePageSizeSelect,
  renderPager,
} from "./qtable"

const KW_FILE = "works_kw.json"

// Campi del record opera come li emette preprocess.mjs (index.json). NON il
// modello di ../English: qui non ci sono cluster/topoi/leggibilita' (Flesch,
// Fog) — quelle colonne mostravano "undefined" perche' il record non le porta.
interface Work {
  href: string
  readHref?: string
  title: string
  author: string
  lang: string
  words: number
  atoms: number
}

let cache: Work[] | null = null
async function loadData(prefix: string): Promise<Work[]> {
  if (cache) return cache
  const res = await fetch(prefix + "static/index.json")
  cache = (await res.json()) as Work[]
  return cache
}

const PAGE_SIZES = [25, 50, 100, 250]

function buildTable(el: HTMLElement, rows: Work[], prefix: string) {
  let sortKey: keyof Work = "title"
  let sortDir = 1
  let filter = ""
  let page = 0
  let pageSize = 50
  let mode: "table" | "content" = "table"

  const search = document.createElement("input")
  search.type = "search"
  search.className = "lt-search"
  const setPlaceholder = () => {
    search.placeholder =
      mode === "content"
        ? `Cerca nel testo completo delle ${rows.length} opere…`
        : `Filtra ${rows.length.toLocaleString("it")} opere per titolo, autore o lingua…`
  }
  setPlaceholder()

  const modeBtn = makeModeToggle({
    label: () => (mode === "content" ? "Search: full content" : "Search: title/author"),
    isContent: () => mode === "content",
    onToggle: () => {
      mode = mode === "table" ? "content" : "table"
      setPlaceholder()
      page = 0
    },
    needKw: () => mode === "content" && !kwCached(KW_FILE),
    loadKw: () => loadKw(prefix, KW_FILE),
    rerender: () => render(),
  })

  const searchRow = document.createElement("div")
  searchRow.className = "qtable-searchrow"
  searchRow.append(search, modeBtn)

  const meta = document.createElement("div")
  meta.className = "lt-meta"

  const table = document.createElement("table")
  table.className = "lt-table"

  const pager = document.createElement("div")
  pager.className = "lt-pager"

  const cols: [keyof Work, string, boolean][] = [
    ["title", "Titolo", false],
    ["author", "Autore", false],
    ["lang", "Lingua", false],
    ["words", "Parole", true],
    ["atoms", "Atomi", true],
  ]
  const NUMERIC = new Set(["words", "atoms"])

  function cmp(a: Work, b: Work): number {
    let av: any = a[sortKey]
    let bv: any = b[sortKey]
    if (NUMERIC.has(sortKey as string)) {
      av = Number(av)
      bv = Number(bv)
      const an = Number.isFinite(av), bn = Number.isFinite(bv)
      if (!an && !bn) return a.title.toLowerCase() < b.title.toLowerCase() ? -1 : 1
      if (!an) return 1 // works without this metric (poetry/theatre) sort last
      if (!bn) return -1
    } else {
      av = noArticle(av)
      bv = noArticle(bv)
    }
    if (av < bv) return -sortDir
    if (av > bv) return sortDir
    return a.title.toLowerCase() < b.title.toLowerCase() ? -1 : 1
  }

  function filtered(): Work[] {
    const q = filter.toLowerCase()
    return rows
      .filter((r) => {
        if (!q) return true
        if (mode === "content") {
          const kw = kwCached(KW_FILE)?.[r.href]
          return kw ? kw.includes(q) : false
        }
        return (
          r.title.toLowerCase().includes(q) ||
          r.author.toLowerCase().includes(q) ||
          (r.lang || "").toLowerCase().includes(q)
        )
      })
      .sort(cmp)
  }

  function render() {
    const all = filtered()
    const pages = Math.max(1, Math.ceil(all.length / pageSize))
    if (page >= pages) page = pages - 1
    if (page < 0) page = 0
    const slice = all.slice(page * pageSize, page * pageSize + pageSize)

    const head =
      "<thead><tr>" +
      cols
        .map(
          ([k, label, num]) =>
            `<th data-k="${k}" class="lt-th${num ? " lt-num" : ""}${
              sortKey === k ? " sorted-" + (sortDir > 0 ? "asc" : "desc") : ""
            }">${label}</th>`,
        )
        .join("") +
      "</tr></thead>"
    const body =
      "<tbody>" +
      slice
        .map(
          (r) =>
            `<tr><td><a href="${prefix}${esc(r.readHref || r.href)}">${esc(r.title)}</a></td>` +
            `<td>${esc(r.author)}</td>` +
            `<td class="lt-lang">${esc(r.lang)}</td>` +
            `<td class="lt-num">${esc(r.words)}</td>` +
            `<td class="lt-num">${esc(r.atoms)}</td></tr>`,
        )
        .join("") +
      "</tbody>"
    table.innerHTML = head + body
    table.querySelectorAll<HTMLElement>("th.lt-th").forEach((th) => {
      th.addEventListener("click", () => {
        const k = th.dataset.k as keyof Work
        if (sortKey === k) sortDir *= -1
        else {
          sortKey = k
          sortDir = NUMERIC.has(k as string) ? -1 : 1
        }
        render()
      })
    })

    meta.innerHTML = `<span><strong>${all.length.toLocaleString("it")}</strong> opere</span>`
    meta.appendChild(
      makePageSizeSelect(PAGE_SIZES, pageSize, (n) => {
        pageSize = n
        page = 0
        render()
      }),
    )

    renderPager(pager, page, pages, (p) => {
      page = p
      render()
    })
  }

  search.addEventListener("input", () => {
    filter = search.value
    page = 0
    render()
  })

  el.replaceChildren(searchRow, meta, table, pager)
  render()
}

async function init() {
  const root = document.getElementById("opere-table")
  if (!root || root.dataset.rendered) return
  root.dataset.rendered = "1"

  const prefix = slugPrefix()

  let data: Work[]
  try {
    data = await loadData(prefix)
  } catch {
    root.textContent = "Could not load the works index."
    return
  }

  // Autore preselezionato: o fissato server-side (root.dataset.author), o
  // scelto cliccando un'emblema in home. wireAuthorCards salva "author::<nome>"
  // in sessionStorage; qui lo si consuma e lo si sgancia, cosi' un ricarico
  // della pagina non lo riapplica.
  let author = root.dataset.author || ""
  try {
    const pre = sessionStorage.getItem("cercaPreselect")
    if (pre && pre.startsWith("author::")) {
      author = pre.slice("author::".length)
      sessionStorage.removeItem("cercaPreselect")
    }
  } catch {}

  let rows = data
  if (author) rows = data.filter((w) => w.author === author)
  buildTable(root, rows, prefix)
}

// Deep-link delegation for the home author cards: store the chosen author in
// sessionStorage and let the /cerca page pick it up. Done via JS so Quartz's
// link sluggifier (which mangles "?"/"=" in hrefs) never sees the parameter.
function wireAuthorCards() {
  document.querySelectorAll<HTMLElement>("a.author-card[data-cerca-author]").forEach((a) => {
    if (a.dataset.wired) return
    a.dataset.wired = "1"
    a.addEventListener("click", () => {
      try {
        sessionStorage.setItem("cercaPreselect", "author::" + a.dataset.cercaAuthor)
      } catch {}
    })
  })
}

document.addEventListener("nav", () => {
  init()
  wireAuthorCards()
})
init()
wireAuthorCards()

export {}
