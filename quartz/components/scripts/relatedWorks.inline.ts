// Append a "related" section to the bottom of the article:
//  - on a work page (slug under "Works/"): "Opere correlate" — works that share
//    the most (and rarest) concept tags (static/related.json).
//  - on any other content page (chapters/scenes): "Capitoli correlati" — units
//    that share the most (and rarest) characters/themes (static/chapter_related.json).
// Both indexes are precomputed in preprocess.mjs, fetched once and cached across
// SPA navigations — no per-note content rewrite needed.

interface WorkRel {
  href: string
  title: string
  author: string
  shared?: number
}
const caches: Record<string, Record<string, unknown[]> | undefined> = {}
const promises: Record<string, Promise<Record<string, unknown[]>> | undefined> = {}
function load(prefix: string, file: string): Promise<Record<string, unknown[]>> {
  if (caches[file]) return Promise.resolve(caches[file]!)
  if (!promises[file]) {
    promises[file] = fetch(prefix + "static/" + file)
      .then((r) => (r.ok ? r.json() : {}))
      .then((j) => (caches[file] = j as Record<string, unknown[]>))
      .catch(() => (caches[file] = {}))
  }
  return promises[file]!
}

function makeSection(heading: string): { section: HTMLElement; ul: HTMLElement } {
  const section = document.createElement("section")
  section.className = "related-works"
  const h = document.createElement("h2")
  h.textContent = heading
  section.appendChild(h)
  const ul = document.createElement("ul")
  section.appendChild(ul)
  return { section, ul }
}

function link(prefix: string, href: string, text: string): HTMLAnchorElement {
  const a = document.createElement("a")
  a.className = "internal"
  a.href = prefix + href
  a.textContent = text
  return a
}

async function init() {
  const slug = document.body.dataset.slug || ""
  const article = document.querySelector("article")
  if (!article || article.querySelector(".related-works")) return
  const prefix = "../".repeat((slug.match(/\//g) || []).length)
  // NB: content slugs are lowercase ("works/..."), so match case-insensitively —
  // a capital-W check silently sent every work page to the chapter index and
  // suppressed "Opere correlate".
  const isWork = slug.toLowerCase().startsWith("works/")
  // Only work-node pages get "Opere correlate" (related.json) here. Reading pages
  // (testi/*) render per-atom "Capitoli correlati" via atomRouter's own per-work
  // shard, so relatedWorks must NOT fetch the chapter index on them.
  if (!isWork) return

  let data: Record<string, unknown[]>
  try {
    data = await load(prefix, "related.json")
  } catch {
    return
  }
  const rels = data[slug]
  if (!rels || !rels.length) return
  // SPA may have navigated away (or another run already injected) while awaiting.
  if ((document.body.dataset.slug || "") !== slug) return
  if (article.querySelector(".related-works")) return

  const { section, ul } = makeSection("Related works")
  for (const r of rels as WorkRel[]) {
    const li = document.createElement("li")
    li.appendChild(link(prefix, r.href, r.title))
    if (r.author) {
      const span = document.createElement("span")
      span.className = "rw-author"
      span.textContent = " — " + r.author
      li.appendChild(span)
    }
    ul.appendChild(li)
  }
  article.appendChild(section)
}

// Bilingual language switch (the OlimpiadiMatematica/qlang pattern). preprocess
// merges the translated body into the page after a `<span class="qlang-split"
// data-lang>` marker, preceded by a `<div class="qlang-switch" data-default>`
// placeholder. Partition the article DOM at the marker into two language groups,
// draw flag buttons, toggle visibility, and persist the choice. Fully client-side
// — no navigation, no server call.
function initLangToggle() {
  const ISO: Record<string, string> = { it: "it", en: "gb" }
  const LABEL: Record<string, string> = { it: "Italiano", en: "English" }
  const sw = document.querySelector(".qlang-switch") as HTMLElement | null
  if (!sw || sw.querySelector(".qlang-btn")) return
  const container = sw.parentElement
  const split = container?.querySelector(".qlang-split") as HTMLElement | null
  if (!container || !split) return

  const defaultLang = sw.dataset.default || "en"
  const otherLang = split.dataset.lang || (defaultLang === "en" ? "it" : "en")
  const langs = [defaultLang, otherLang]

  const groups: Record<string, HTMLElement[]> = { [defaultLang]: [], [otherLang]: [] }
  let cur = defaultLang
  for (const node of Array.from(container.children) as HTMLElement[]) {
    if (node === sw) continue
    if (node.classList.contains("qlang-split") || node.contains(split)) {
      cur = otherLang
      continue
    }
    groups[cur].push(node)
  }

  const bp = document.body.dataset.basepath || ""
  // Always open in the page's default language (English). A previously chosen
  // language is NOT made the global sticky default — the toggle only switches the
  // current view. This keeps every work opening in EN as requested.
  let active = defaultLang

  function apply(lang: string) {
    for (const l of langs) for (const n of groups[l]) n.style.display = l === lang ? "" : "none"
    sw.querySelectorAll("button").forEach((b) =>
      b.classList.toggle("active", (b as HTMLElement).dataset.lang === lang),
    )
    active = lang
  }

  sw.replaceChildren()
  for (const l of langs) {
    const b = document.createElement("button")
    b.type = "button"
    b.dataset.lang = l
    b.className = "qlang-btn"
    b.title = LABEL[l] || l
    const iso = ISO[l]
    if (iso) {
      const img = document.createElement("img")
      img.className = "qlang-flag"
      img.src = `${bp}/static/flags/${iso}.svg`
      img.alt = LABEL[l] || l
      img.loading = "lazy"
      b.appendChild(img)
    } else {
      b.textContent = l.toUpperCase()
    }
    b.addEventListener("click", () => {
      apply(l)
    })
    sw.appendChild(b)
  }
  apply(active)
}

document.addEventListener("nav", () => {
  init()
  initLangToggle()
})
init()
initLangToggle()

export {}
