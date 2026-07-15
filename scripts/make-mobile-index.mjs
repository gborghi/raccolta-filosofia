// Post-build: derive a LIGHT search index for mobile from the full contentIndex.json.
// Mobile browsers OOM parsing the full ~27MB index; this keeps title/tags/links + a
// short content snippet so the on-device FlexSearch build stays small. Desktop keeps
// the full index (loaded via fetchData); only mobile fetches contentIndexMobile.json.
// Run AFTER `npx quartz build`, before uploading the Pages artifact.
import fs from "fs"
import path from "path"

const dir = "public/static"
const full = path.join(dir, "contentIndex.json")
const outPath = path.join(dir, "contentIndexMobile.json")
const SNIPPET = 80 // chars of content kept per entry
const LINK_CAP = 20 // keep up to N links/entry so the GRAPH still works on mobile
                    // (works have ~10 links; only huge aggregator hubs get trimmed)

if (!fs.existsSync(full)) {
  console.error(`make-mobile-index: ${full} not found — skipping`)
  process.exit(0)
}
const raw = JSON.parse(fs.readFileSync(full, "utf8"))
// contentIndex.json top level is a map slug -> item (defensive: unwrap {content:{...}})
const map = raw && raw.content && typeof raw.content === "object" && !raw.content.slug ? raw.content : raw
const out = {}
for (const [slug, it] of Object.entries(map)) {
  if (!it || typeof it !== "object") continue
  // Keep links (capped) so the graph works on mobile too; drop filePath (unused).
  // Aggregator notes carry huge links[] (every work) — cap trims those hubs only.
  out[slug] = {
    slug: it.slug,
    title: it.title,
    tags: it.tags,
    links: Array.isArray(it.links) ? it.links.slice(0, LINK_CAP) : [],
    content: typeof it.content === "string" ? it.content.slice(0, SNIPPET) : "",
  }
}
const json = JSON.stringify(out)
fs.writeFileSync(outPath, json)
const fullSize = fs.statSync(full).size
console.log(
  `make-mobile-index: ${Object.keys(out).length} entries | ` +
    `${(fullSize / 1e6).toFixed(1)}MB -> ${(json.length / 1e6).toFixed(1)}MB (mobile)`,
)
