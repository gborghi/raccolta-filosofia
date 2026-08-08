// Post-build: derive a LIGHT search index for mobile from the MASTER full ranked
// index (data/search-full-index.json, built by compress-search-index.mjs). Mobile
// browsers OOM parsing the full ~27MB desktop index; this projects the master down
// to a small byte budget via the same size-targeted binary search desktop uses, so
// both indexes derive from ONE TF-IDF pass instead of recomputing it twice.
// Desktop keeps its own projection (loaded via fetchData); only mobile fetches
// contentIndexMobile.json.
// MUST run AFTER compress-search-index.mjs (which builds the master) — fails
// loudly if the master is missing rather than silently skipping.
import fs from "fs"
import path from "path"
import { projectToTarget } from "./compress-search-index.mjs"

const masterPath = path.join("data", "search-full-index.json")
// QUARTZ_OUT lets the whole post-build chain target a directory other than public/.
// Needed on Windows, where Dropbox or the indexer can hold a handle on public/ that
// makes Quartz's initial wipe fail with EBUSY — building elsewhere sidesteps the lock
// instead of retrying against it. CI sets nothing and keeps public/.
const OUT = process.env.QUARTZ_OUT || "public"
const outPath = path.join(OUT, "static", "contentIndexMobile.json")
const MOBILE_TARGET = 8_000_000 // bytes; mobile contentIndexMobile.json budget
const LINK_CAP = 20 // keep up to N links/entry so the GRAPH still works on mobile
// (works have ~10 links; only huge aggregator hubs get trimmed)
const FIELDS = ["slug", "title", "tags", "links"]

if (!fs.existsSync(masterPath)) {
  console.error(
    `make-mobile-index: master ${masterPath} not found — compress-search-index.mjs must run first (fatal)`,
  )
  process.exit(1)
}

const master = JSON.parse(fs.readFileSync(masterPath, "utf8"))

// Cap links BEFORE projecting so the binary search sizes against the actual bytes
// that end up on disk (capping after projection would let the chosen term count
// undershoot the target once the trimmed links shrink the final payload).
// Mobile index is works-only. Per-atom search entries (keys `workSlug#atomId`)
// are a DESKTOP searchbar enhancement: they carry no `terms`, so the byte-budget
// projection has no field to trim on them — 19k atom entries would pin the mobile
// index at its per-entry floor (~12.8MB) regardless of target. Dropping them
// restores mobile to its natural works-only size (~7.5MB, under budget). Desktop
// (contentIndex.json) keeps the full per-leaf index.
const capped = {}
for (const [slug, d] of Object.entries(master)) {
  if (slug.includes("#")) continue
  capped[slug] = { ...d, links: Array.isArray(d.links) ? d.links.slice(0, LINK_CAP) : [] }
}

const projected = projectToTarget(capped, MOBILE_TARGET, FIELDS)
const json = JSON.stringify(projected)
fs.writeFileSync(outPath, json)

const masterSize = fs.statSync(masterPath).size
console.log(
  `make-mobile-index: ${Object.keys(projected).length} entries | ` +
    `master ${(masterSize / 1e6).toFixed(1)}MB -> ${(json.length / 1e6).toFixed(1)}MB (mobile)`,
)
