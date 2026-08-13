// Build the 4 tiered search shards from the TF-IDF master (data/search-full-index.json).
// Each tier's `content` is a SUPERSET of the previous (snippet+terms grow monotonically),
// so the client deepens by REPLACING doc content by slug — no term-union bookkeeping.
// Emits public/static/search-t{0,1,2,3}.json. Run AFTER compress-search-index.mjs
// (which builds the master, including injected `#`-keyed atom entries).
//
// Shard file shape: {"tier":N,"entries":[{s,t,g,c},…]} (full shape) or {s,c} (delta).
// Delta shards (t1,t3) carry only {s,c} (content replacement for existing slugs); t2
// carries full new atom entries; t3 is a full-depth delta for BOTH works and atoms.
// Compact keys: s=slug t=title g=tags c=content. `l` (links) is dropped: the search
// client indexes only title/content/tags and never reads links (the graph + backlinks
// read them from contentIndex.json instead), so it was pure dead weight in the shards.
import fs from "fs"
import path from "path"
import { pathToFileURL } from "node:url"

const masterPath = path.join("data", "search-full-index.json")
// see the QUARTZ_OUT note in make-mobile-index.mjs
const outDir = path.join(process.env.QUARTZ_OUT || "public", "static")
// HARD_CAP = the real guard: Cloudflare Pages rejects any single file > 25 MiB
// (26,214,400 bytes), so fail the build at that ceiling. SOFT = per-tier size budget we
// target (progressive-load budget); exceeding it only warns — real sizes get reported
// either way. The HIGHEST tier (Max) is budgeted at 90% of the Cloudflare cap, and each
// lower tier scales down, with the two smallest (Fast/Standard — the only tiers a phone
// loads; the slider clamps to ≤1 on mobile) kept phone-sized (<5MB).
const CLOUDFLARE_MAX = 25 * 1024 * 1024 // 26,214,400 bytes
const HARD_CAP = CLOUDFLARE_MAX
const TOP_TIER_BYTES = Math.floor(CLOUDFLARE_MAX * 0.9) // 23,592,960 bytes = 90%
const SOFT = { 0: 4_500_000, 1: 5_000_000, 2: TOP_TIER_BYTES, 3: TOP_TIER_BYTES }

const isAtom = (slug) => slug.includes("#")

// Generated navigation shells, kept out of the results list. They hold no prose of
// their own — the wheel and the excerpt table are rendered client-side — so they can
// only ever match on their own chrome, and they rank first on any generic query
// because their slugs are one segment long. The left sidebar already hides them
// (see the explorer `filterFn` in quartz.config.yaml); this is the search half.
export const HIDDEN_SLUGS = new Set(["index", "brani", "404"])

// Same story at scale: Quartz generates one page per tag (~3.7k of them), each holding
// nothing but its own tag name and the list of members — no prose, empty `terms`/`snippet`
// in the master — so they can only match on chrome yet crowd out real pages. The browsable
// tag INDEX (`tags/index`, the table gen-tags-table.mjs builds) is a real destination and
// stays searchable; only the per-tag shells below it go.
export const TAGS_INDEX_SLUG = "tags/index"
export const isHiddenSlug = (slug) =>
  HIDDEN_SLUGS.has(slug) || (slug.startsWith("tags/") && slug !== TAGS_INDEX_SLUG)

// contentFor(doc, n, S): readable S-char snippet + top-n ranked terms.
export function contentFor(doc, n, S) {
  const snip = (doc.snippet || "").slice(0, S)
  const terms = (Array.isArray(doc.terms) ? doc.terms : [])
    .slice(0, n)
    .map(([w]) => w)
    .join(" ")
  return snip ? `${snip} ${terms}` : terms
}

// buildShards(master) -> { t0, t1, t2, t3 }; each { tier, entries }.
export function buildShards(master) {
  const works = []
  const atoms = []
  for (const [slug, d] of Object.entries(master)) {
    if (isHiddenSlug(slug)) continue
    ;(isAtom(slug) ? atoms : works).push([slug, d])
  }

  const t0 = works.map(([s, d]) => ({
    s,
    t: d.title || "",
    g: d.tags || [],
    c: contentFor(d, 30, 160),
  }))
  const t1 = works.map(([s, d]) => ({ s, c: contentFor(d, 150, 400) }))
  const t2 = atoms.map(([s, d]) => ({
    s,
    t: d.title || "",
    g: d.tags || [],
    c: contentFor(d, 80, 400),
  }))
  // t3 = Max: full depth on EVERYTHING. Works deepen top150/400 -> top500/700, and atoms
  // deepen top80/400 -> top500/700. Atoms are NOT fully covered at 80 terms — most carry
  // more ranked terms and longer snippets — so the Max deepening adds real per-chapter
  // recall, not padding. This is the HIGHEST tier: the largest shard, budgeted at 90% of
  // the Cloudflare per-file cap.
  const t3 = [
    ...works.map(([s, d]) => ({ s, c: contentFor(d, 500, 700) })),
    ...atoms.map(([s, d]) => ({ s, c: contentFor(d, 500, 700) })),
  ]
  return {
    t0: { tier: 0, entries: t0 },
    t1: { tier: 1, entries: t1 },
    t2: { tier: 2, entries: t2 },
    t3: { tier: 3, entries: t3 },
  }
}

// Split entries into contiguous buckets each serializing under ~targetBytes, so the
// atom tier stays under the Cloudflare per-file cap however large the corpus grows.
// Deterministic (insertion order), so builds are reproducible.
export function chunkBySize(entries, targetBytes) {
  const buckets = []
  let cur = []
  let curBytes = 2 // "[]"
  for (const e of entries) {
    const b = Buffer.byteLength(JSON.stringify(e)) + 1 // + comma
    if (cur.length && curBytes + b > targetBytes) {
      buckets.push(cur)
      cur = []
      curBytes = 2
    }
    cur.push(e)
    curBytes += b
  }
  if (cur.length) buckets.push(cur)
  return buckets
}

function main() {
  if (!fs.existsSync(masterPath)) {
    console.error(
      `build-search-shards: ${masterPath} not found — compress-search-index.mjs must run first (fatal)`,
    )
    process.exit(1)
  }
  const master = JSON.parse(fs.readFileSync(masterPath, "utf8"))
  const shards = buildShards(master)
  fs.mkdirSync(outDir, { recursive: true })

  const writeShard = (name, obj, tier) => {
    const json = JSON.stringify(obj)
    const bytes = Buffer.byteLength(json)
    if (bytes > HARD_CAP) {
      console.error(
        `build-search-shards: ${name} = ${(bytes / 1e6).toFixed(1)}MB exceeds the 25MB ` +
          `Cloudflare hard cap (fatal)`,
      )
      process.exit(1)
    }
    const warn = bytes > SOFT[tier] ? " ⚠ over soft target" : ""
    fs.writeFileSync(path.join(outDir, name), json)
    const n = obj.entries ? obj.entries.length : ""
    console.log(`build-search-shards: ${name} = ${(bytes / 1e6).toFixed(2)}MB (${n} entries)${warn}`)
  }

  // Single-file tiers (the two phone tiers).
  writeShard("search-t0.json", shards.t0, 0)
  writeShard("search-t1.json", shards.t1, 1)

  // Bucketed tiers (t2 atoms, t3 full-depth): chunk under the soft target so no single
  // file nears the CF cap, and emit a manifest the client reads to know the bucket count.
  const writeBucketed = (tier, entries, prefix) => {
    const buckets = chunkBySize(entries, SOFT[tier])
    const files = buckets.map((_, i) => `${prefix}-${i}.json`)
    buckets.forEach((b, i) => writeShard(files[i], { tier, entries: b }, tier))
    fs.writeFileSync(path.join(outDir, `${prefix}.json`), JSON.stringify({ tier, buckets: files }))
    console.log(
      `build-search-shards: ${prefix}.json manifest -> ${files.length} buckets (${entries.length} entries)`,
    )
  }
  writeBucketed(2, shards.t2.entries, "search-t2")
  writeBucketed(3, shards.t3.entries, "search-t3")
}

// cross-platform main-guard: `file://${argv[1]}` breaks on Windows (backslashes,
// drive-letter slash) — pathToFileURL normalizes both to the same file: URL.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main()
