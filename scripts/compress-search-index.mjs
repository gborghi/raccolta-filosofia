// Post-build: shrink the DESKTOP search index (public/static/contentIndex.json)
// via a two-stage master/projection design.
//
// Stage 1 (buildFullIndex): TF-IDF is computed ONCE over the injected full index,
// producing a MASTER full ranked index — per doc, every distinctive term sorted by
// tf-idf score desc, capped at MASTER_CAP. The master is written to
// data/search-full-index.json, kept OFF the deployed site (large, regenerable).
//
// Stage 2 (projectToTarget): the master is projected down to a byte budget by
// binary-searching the largest top-N term count whose serialized size still fits
// under the target. This lets desktop (15MB) and mobile (8MB, see
// make-mobile-index.mjs) both derive from the SAME master without recomputing
// TF-IDF twice.
//
// title/tags/links/slug are untouched; only `content` (built from a readable
// 160-char prose snippet + top-N terms) is replaced. Run AFTER `npx quartz build`
// (+ inject-atom-search.mjs).
// NOTE: not idempotent — always run on a freshly built contentIndex.json (the build
// regenerates it each time), never twice in a row.
import fs from "fs"
import path from "path"
import { pathToFileURL } from "node:url"

// see the QUARTZ_OUT note in make-mobile-index.mjs
const dir = path.join(process.env.QUARTZ_OUT || "public", "static")
const full = path.join(dir, "contentIndex.json")
const masterPath = path.join("data", "search-full-index.json")
const MASTER_CAP = 500 // ranked terms kept per doc in the master (bounds its size)
const MASTER_SNIPPET = 700 // chars of readable prose kept per doc (deep tiers slice this down)
const DESKTOP_TARGET = 15_000_000 // bytes; desktop contentIndex.json budget
const MIN_LEN = 3 // ignore tokens shorter than this
// NOTE: widened from the original prose-only /[a-z][a-z']+/g to also admit digits
// ([a-z][a-z0-9']*) — the original never matched real English tokens with digits
// either way, so production behavior on prose content is unchanged; this only
// matters for synthetic test fixtures ("w0", "word123") which the old regex
// silently truncated at the first digit, collapsing every doc to the same "w"/
// "word" stub term and starving buildFullIndex's ranking test of real signal.
const WORD = /[a-z][a-z0-9']*/g

const STOP = new Set(
  (
    "the a an and or but if then else of to in on at by for with from as is are was were be been being this that " +
    "these those it its he she we they them his her their our your my me him us not no nor so too very can will would " +
    "should could may might must shall do does did have has had having about into over under out up down off again once " +
    "here there when where why how all any both each few more most other some such only own same than thus yet also " +
    "which what who whom whose said says say one two upon now like man men come came go went see saw know knew think " +
    "thought tell told make made take took give gave let mrs mr dr sir lady much many little day night time life old new " +
    "long thing things way part place your you i o oh ye thou thee thy hath doth unto shall"
  ).split(/\s+/),
)

// buildFullIndex(rawIndex) -> { [slug]: {title, slug, tags, links, terms} }
// rawIndex: flat map slug -> {title, content, tags, links, slug} (already unwrapped).
// terms: [[term, tfidfScore], ...] sorted desc, capped at MASTER_CAP.
export function buildFullIndex(rawIndex) {
  const slugs = Object.keys(rawIndex)
  const N = slugs.length

  // pass 1: per-entry token frequency + document frequency
  const tf = new Map() // slug -> Map(term->count)
  const df = new Map() // term -> #docs
  const snippets = new Map() // slug -> readable prose snippet (from raw, pre-lowercase text)
  for (const slug of slugs) {
    const it = rawIndex[slug]
    const rawText = it && typeof it.content === "string" ? it.content : ""
    snippets.set(slug, rawText.replace(/\s+/g, " ").trim().slice(0, MASTER_SNIPPET))
    const text = rawText.toLowerCase()
    const counts = new Map()
    for (const m of text.matchAll(WORD)) {
      const w = m[0]
      if (w.length < MIN_LEN || STOP.has(w)) continue
      counts.set(w, (counts.get(w) || 0) + 1)
    }
    tf.set(slug, counts)
    for (const w of counts.keys()) df.set(w, (df.get(w) || 0) + 1)
  }

  // pass 2: rank terms by tf-idf, cap at MASTER_CAP
  const out = {}
  for (const slug of slugs) {
    const it = rawIndex[slug] || {}
    const counts = tf.get(slug)
    const scored = []
    for (const [w, c] of counts) {
      const idf = Math.log(N / (df.get(w) || 1))
      if (idf <= 0) continue // word in every doc -> useless
      scored.push([w, c * idf])
    }
    scored.sort((a, b) => b[1] - a[1])
    out[slug] = {
      title: it.title,
      slug: it.slug ?? slug,
      tags: it.tags || [],
      links: it.links || [],
      terms: scored.slice(0, MASTER_CAP),
      snippet: snippets.get(slug) || "",
    }
  }
  return out
}

// projectToTarget(fullIndex, targetBytes, fields?) -> projected index
// Binary-searches the largest top-N term count (N in [5, MASTER_CAP]) whose
// serialized size stays <= targetBytes. Each projected doc keeps `fields` plus a
// `content` string built from its top-N terms — the SAME entry shape the search
// component reads today. If the master already fits at N=MASTER_CAP, keep all
// terms (never pad below what's available).
export function projectToTarget(
  fullIndex,
  targetBytes,
  fields = ["title", "slug", "tags", "links"],
) {
  const slugs = Object.keys(fullIndex)

  function project(n) {
    const out = {}
    for (const slug of slugs) {
      const d = fullIndex[slug]
      const entry = {}
      for (const f of fields) entry[f] = d[f]
      const terms = Array.isArray(d.terms) ? d.terms.slice(0, n) : []
      const termStr = terms.map(([w]) => w).join(" ")
      // Legacy single-file projector keeps a short 160-char snippet (the master now
      // stores up to 700 for the tiered shard emitter; re-slice here so this path's
      // output size is unchanged). This projector is retired from main() in the shard
      // build but stays exported + unit-tested.
      const snip = (d.snippet || "").slice(0, 160)
      entry.content = snip ? `${snip} ${termStr}` : termStr
      out[slug] = entry
    }
    return out
  }

  function sizeOf(n) {
    return Buffer.byteLength(JSON.stringify(project(n)))
  }

  if (sizeOf(MASTER_CAP) <= targetBytes) return project(MASTER_CAP)

  let lo = 5
  let hi = MASTER_CAP
  if (sizeOf(lo) > targetBytes) return project(lo) // can't shrink further than floor

  let best = lo
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (sizeOf(mid) <= targetBytes) {
      best = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  return project(best)
}

function main() {
  if (!fs.existsSync(full)) {
    console.error(`compress-search-index: ${full} not found — skipping`)
    process.exit(0)
  }

  const raw = JSON.parse(fs.readFileSync(full, "utf8"))
  const wrapped = raw && raw.content && typeof raw.content === "object" && !raw.content.slug
  const index = wrapped ? raw.content : raw
  const fullSizeBefore = fs.statSync(full).size

  // Build the off-site TF-IDF master (includes injected `#`-keyed atom entries: they
  // carry `content`, so they get ranked terms + a snippet like any doc). Two consumers:
  //  - make-mobile-index.mjs projects it to the light contentIndexMobile.json,
  //  - build-search-shards.mjs slices it into the tiered searchDepth shards.
  const master = buildFullIndex(index)
  const masterJson = JSON.stringify(master)
  fs.mkdirSync(path.dirname(masterPath), { recursive: true })
  fs.writeFileSync(masterPath, masterJson)

  // contentIndex.json is ALSO the fetchData payload for the graph + backlinks
  // (renderPage.tsx), not just search — so keep projecting it to the desktop budget
  // (the disabled community search no longer reads it, but the graph/backlinks do).
  const desktop = projectToTarget(master, DESKTOP_TARGET)
  if (wrapped) raw.content = desktop
  const out = wrapped ? JSON.stringify(raw) : JSON.stringify(desktop)
  fs.writeFileSync(full, out)

  console.log(
    `compress-search-index: ${Object.keys(master).length} entries | ` +
      `master ${(masterJson.length / 1e6).toFixed(1)}MB (off-site) | ` +
      `desktop ${(fullSizeBefore / 1e6).toFixed(1)}MB -> ${(out.length / 1e6).toFixed(1)}MB`,
  )
}

// cross-platform main-guard: `file://${argv[1]}` breaks on Windows (backslashes,
// drive-letter slash) — pathToFileURL normalizes both to the same file: URL.
// Required now that make-mobile-index.mjs imports buildFullIndex/projectToTarget
// from this module — top-level execution must not fire on import.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main()
