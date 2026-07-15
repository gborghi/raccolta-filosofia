// Shared helpers for the client-side table scripts (opere / brani / cerca / concept).
// Imported into each *.inline.ts; the inline-script loader (componentResources bundles
// each inline script separately via esbuild) inlines this module into every bundle, so
// this is a source-dedup / consistency win, not a shipped-JS one.

export function esc(s: unknown): string {
  return String(s).replace(/[&<>"]/g, (c) =>
    c === "&" ? "&amp;" : c === "<" ? "&lt;" : c === ">" ? "&gt;" : "&quot;",
  )
}

// "../" depth from the current page slug, for prefixing static/ + internal links.
export function slugPrefix(): string {
  const slug = document.body.dataset.slug || ""
  return "../".repeat((slug.match(/\//g) || []).length)
}

// Sort key that ignores a leading article ("The Waste Land" sorts under W).
export function noArticle(s: unknown): string {
  return String(s).toLowerCase().replace(/^\s*(the|a|an)\s+/, "").trim()
}

// ONE keyword-index cache shared across all table scripts, keyed by filename — so
// /opere, /cerca and concept pages that all read works_kw.json fetch it once total
// (previously each script kept its own cache and re-fetched).
const kwCaches: Record<string, Record<string, string>> = {}
const kwPromises: Record<string, Promise<Record<string, string>>> = {}
export function loadKw(prefix: string, file: string): Promise<Record<string, string>> {
  if (kwCaches[file]) return Promise.resolve(kwCaches[file])
  if (!kwPromises[file]) {
    kwPromises[file] = fetch(prefix + "static/" + file)
      .then((r) => r.json())
      .then((j) => (kwCaches[file] = j as Record<string, string>))
  }
  return kwPromises[file]
}
export function kwCached(file: string): Record<string, string> | undefined {
  return kwCaches[file]
}

// The "Search: title/author ↔ full content" toggle button. Owns only its own DOM +
// label sync + lazy kw load; the caller owns the mode/page state via callbacks.
export function makeModeToggle(opts: {
  label: () => string
  isContent: () => boolean
  onToggle: () => void // flip mode, reset page, update placeholder (caller-owned state)
  needKw: () => boolean // mode is content and its kw index isn't loaded yet
  loadKw: () => Promise<unknown>
  rerender: () => void
}): HTMLButtonElement {
  const btn = document.createElement("button")
  btn.type = "button"
  btn.className = "qtable-modebtn"
  const sync = () => {
    btn.textContent = opts.label()
    btn.setAttribute("aria-pressed", String(opts.isContent()))
  }
  sync()
  btn.addEventListener("click", async () => {
    opts.onToggle()
    sync()
    if (opts.needKw()) {
      btn.textContent = "Loading index..."
      btn.disabled = true
      try {
        await opts.loadKw()
      } catch {}
      btn.disabled = false
      sync()
    }
    opts.rerender()
  })
  return btn
}

// A page-size <select> (0 -> "All"). onChange gets the chosen size.
export function makePageSizeSelect(
  sizes: number[],
  current: number,
  onChange: (n: number) => void,
): HTMLSelectElement {
  const sel = document.createElement("select")
  for (const s of sizes) {
    const o = document.createElement("option")
    o.value = String(s)
    o.textContent = s === 0 ? "All" : `${s} / page`
    if (s === current) o.selected = true
    sel.appendChild(o)
  }
  sel.addEventListener("change", () => onChange(Number(sel.value)))
  return sel
}

// First/Prev/‹info›/Next/Last pager into `container`. goto(pageIndex) is 0-based; the
// caller clamps in its render. Replaces the three drifted copies (opere inlined it,
// brani/concept used a local mk()).
export function renderPager(
  container: HTMLElement,
  page: number,
  pages: number,
  goto: (p: number) => void,
): void {
  container.innerHTML = ""
  const mk = (label: string, disabled: boolean, p: number) => {
    const b = document.createElement("button")
    b.textContent = label
    b.disabled = disabled
    b.addEventListener("click", () => goto(p))
    return b
  }
  const info = document.createElement("span")
  info.className = "lt-page-info"
  info.textContent = `Page ${page + 1} of ${pages}`
  container.append(
    mk("« First", page === 0, 0),
    mk("‹ Prev", page === 0, page - 1),
    info,
    mk("Next ›", page >= pages - 1, page + 1),
    mk("Last »", page >= pages - 1, pages - 1),
  )
}
