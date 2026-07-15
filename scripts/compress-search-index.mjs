// Post-build: shrink the DESKTOP search index (public/static/contentIndex.json).
// The full index stores each page's entire text, which balloons to ~300MB across ~23k
// pages. FlexSearch only needs discriminating tokens to match, so we replace each
// entry's `content` with a short readable snippet + its top TF-IDF terms:
//   - snippet (first ~160 chars of real text) keeps search-result previews legible;
//   - top-N TF-IDF terms keep the page findable by its distinctive words.
// title/tags/links/slug are untouched. Run AFTER `npx quartz build`.
// NOTE: not idempotent — always run on a freshly built contentIndex.json (the build
// regenerates it each time), never twice in a row.
import fs from "fs"
import path from "path"

const dir = "public/static"
const full = path.join(dir, "contentIndex.json")
const TOP_TERMS = 50 // distinctive words kept per page
const SNIPPET = 160 // chars of real text kept for a readable preview
const MIN_LEN = 3 // ignore tokens shorter than this

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

if (!fs.existsSync(full)) {
  console.error(`compress-search-index: ${full} not found — skipping`)
  process.exit(0)
}

const raw = JSON.parse(fs.readFileSync(full, "utf8"))
const map =
  raw && raw.content && typeof raw.content === "object" && !raw.content.slug ? raw.content : raw
const slugs = Object.keys(map)
const N = slugs.length
const WORD = /[a-z][a-z']+/g

// pass 1: per-entry token frequency + document frequency
const tf = new Map() // slug -> Map(term->count)
const df = new Map() // term -> #docs
for (const slug of slugs) {
  const it = map[slug]
  const text = (it && typeof it.content === "string" ? it.content : "").toLowerCase()
  const counts = new Map()
  for (const m of text.matchAll(WORD)) {
    const w = m[0]
    if (w.length < MIN_LEN || STOP.has(w)) continue
    counts.set(w, (counts.get(w) || 0) + 1)
  }
  tf.set(slug, counts)
  for (const w of counts.keys()) df.set(w, (df.get(w) || 0) + 1)
}

// pass 2: rewrite content = snippet + top TF-IDF terms
const fullSize = fs.statSync(full).size
for (const slug of slugs) {
  const it = map[slug]
  if (!it || typeof it !== "object") continue
  const orig = typeof it.content === "string" ? it.content : ""
  const snippet = orig.slice(0, SNIPPET)
  const counts = tf.get(slug)
  const scored = []
  for (const [w, c] of counts) {
    const idf = Math.log(N / (df.get(w) || 1))
    if (idf <= 0) continue // word in every doc -> useless
    scored.push([w, c * idf])
  }
  scored.sort((a, b) => b[1] - a[1])
  const inSnippet = new Set(snippet.toLowerCase().match(WORD) || [])
  const terms = []
  for (const [w] of scored) {
    if (terms.length >= TOP_TERMS) break
    if (!inSnippet.has(w)) terms.push(w)
  }
  it.content = terms.length ? `${snippet} ${terms.join(" ")}` : snippet
}

const out = JSON.stringify(raw)
fs.writeFileSync(full, out)
console.log(
  `compress-search-index: ${N} entries | ${(fullSize / 1e6).toFixed(1)}MB -> ` +
    `${(out.length / 1e6).toFixed(1)}MB (snippet ${SNIPPET} + top-${TOP_TERMS} tf-idf)`,
)
