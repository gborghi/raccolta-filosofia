import test from "node:test"
import assert from "node:assert/strict"
import { buildShards, contentFor, chunkBySize, isHiddenSlug } from "./build-search-shards.mjs"

const master = {
  "works/w1": {
    title: "W1",
    slug: "works/w1",
    tags: ["x"],
    links: ["works/w2"],
    snippet: "s".repeat(700),
    terms: Array.from({ length: 500 }, (_, i) => [`term${i}`, 500 - i]),
  },
  index: {
    title: "English Literature — A Knowledge Graph",
    slug: "index",
    tags: [],
    links: ["brani"],
    snippet: "homepage chrome",
    terms: [["graph", 1]],
  },
  brani: {
    title: "Brani / Excerpts",
    slug: "brani",
    tags: [],
    links: [],
    snippet: "excerpt table chrome",
    terms: [["excerpts", 1]],
  },
  "tags/amore": {
    title: "Tag: amore",
    slug: "tags/amore",
    tags: [],
    links: [],
    snippet: "",
    terms: [],
  },
  "tags/index": {
    title: "Tag Index",
    slug: "tags/index",
    tags: [],
    links: [],
    snippet: "",
    terms: [],
  },
  404: {
    title: "404 — Not Found",
    slug: "404",
    tags: [],
    links: [],
    snippet: "not found chrome",
    terms: [["found", 1]],
  },
  "testi/w1#a2": {
    title: "A2 — W1",
    slug: "testi/w1#a2",
    tags: [],
    links: ["works/w1"],
    snippet: "atomtext ".repeat(100).trim(),
    terms: Array.from({ length: 500 }, (_, i) => [`av${i}`, 1]),
  },
}

test("contentFor slices snippet + top-n terms", () => {
  const c = contentFor(master["works/w1"], 30, 160)
  assert.equal(c.slice(0, 160), "s".repeat(160))
  assert.ok(c.includes("term0"))
  assert.ok(c.includes("term29"))
  assert.ok(!/\bterm30\b/.test(c))
})

test("t0 = works/concepts only, top30/160; excludes '#' atoms; no dead links", () => {
  const { t0 } = buildShards(master)
  const slugs = t0.entries.map((e) => e.s)
  assert.ok(slugs.includes("works/w1"))
  assert.ok(!slugs.some((s) => s.includes("#")))
  const e = t0.entries.find((e) => e.s === "works/w1")
  assert.deepEqual(Object.keys(e).sort(), ["c", "g", "s", "t"])
  assert.ok(!("l" in e), "t0 must drop the dead `l` (links) field")
  assert.ok(e.c.includes("term29") && !/\bterm30\b/.test(e.c))
})

test("t1 delta = works, {s,c} only, top150/400 (superset of t0)", () => {
  const { t1 } = buildShards(master)
  const e = t1.entries.find((e) => e.s === "works/w1")
  assert.deepEqual(Object.keys(e).sort(), ["c", "s"])
  assert.ok(e.c.includes("term149") && !/\bterm150\b/.test(e.c))
  assert.equal(e.c.slice(0, 400), "s".repeat(400))
})

test("t2 = atom entries only, full shape, top80 (no dead links)", () => {
  const { t2 } = buildShards(master)
  assert.equal(t2.entries.length, 1)
  const e = t2.entries[0]
  assert.equal(e.s, "testi/w1#a2")
  assert.deepEqual(Object.keys(e).sort(), ["c", "g", "s", "t"])
  assert.ok(!("l" in e), "t2 must drop the dead `l` (links) field")
  assert.ok(e.c.includes("av79") && !/\bav80\b/.test(e.c))
})

test("t3 = Max delta: works AND atoms at full depth, {s,c} only", () => {
  const { t3 } = buildShards(master)
  const w = t3.entries.find((e) => e.s === "works/w1")
  assert.ok(w.c.includes("term499"))
  assert.equal(w.c.slice(0, 700), "s".repeat(700))
  assert.deepEqual(Object.keys(w).sort(), ["c", "s"])
  const a = t3.entries.find((e) => e.s === "testi/w1#a2")
  assert.ok(a, "t3 must also ship the atom at full depth")
  assert.deepEqual(Object.keys(a).sort(), ["c", "s"])
  assert.ok(a.c.includes("av499"), "Max atoms carry all 500 ranked terms, not just 80")
  assert.ok(a.c.includes("av79"))
})

test("navigation shells (index, brani, 404, per-tag pages) are in no tier", () => {
  const shards = buildShards(master)
  for (const t of ["t0", "t1", "t2", "t3"]) {
    const slugs = shards[t].entries.map((e) => e.s)
    assert.ok(!slugs.includes("index"), `${t} still ships the homepage`)
    assert.ok(!slugs.includes("brani"), `${t} still ships the excerpt index`)
    assert.ok(!slugs.includes("404"), `${t} still ships the 404 page`)
    assert.ok(!slugs.includes("tags/amore"), `${t} still ships a per-tag shell`)
  }
})

test("the browsable tag index survives the per-tag cull", () => {
  const { t0, t1, t3 } = buildShards(master)
  for (const [name, shard] of [
    ["t0", t0],
    ["t1", t1],
    ["t3", t3],
  ]) {
    assert.ok(
      shard.entries.some((e) => e.s === "tags/index"),
      `${name} dropped the tag index page`,
    )
  }
})

test("isHiddenSlug hides per-tag pages but not the tag index or real pages", () => {
  assert.ok(isHiddenSlug("tags/amore"))
  assert.ok(isHiddenSlug("404"))
  assert.ok(!isHiddenSlug("tags/index"))
  assert.ok(!isHiddenSlug("tags")) // the listing's own bare slug, if ever emitted
  assert.ok(!isHiddenSlug("works/w1"))
})

test("chunkBySize splits into size-bounded contiguous buckets covering all entries", () => {
  const entries = Array.from({ length: 20 }, (_, i) => ({ s: `a${i}`, c: "x".repeat(100) }))
  const buckets = chunkBySize(entries, 400) // each entry ~ >100 bytes → a few per bucket
  assert.ok(buckets.length > 1)
  for (const b of buckets) assert.ok(Buffer.byteLength(JSON.stringify(b)) <= 400 || b.length === 1)
  assert.deepEqual(
    buckets.flat().map((e) => e.s),
    entries.map((e) => e.s), // order + completeness preserved
  )
})
