import test from "node:test"
import assert from "node:assert/strict"
import {
  entryToDoc,
  mergeTier,
  clampStop,
  STOP_LABELS,
  stopHint,
  mergeResults,
} from "./searchDepth"

test("entryToDoc maps compact keys", () => {
  const d = entryToDoc({ s: "works/w", t: "W", g: ["x"], l: ["works/y"], c: "hello world" })
  assert.deepEqual(d, {
    id: "works/w",
    slug: "works/w",
    title: "W",
    content: "hello world",
    tags: ["x"],
    links: ["works/y"],
  })
})

test("mergeTier adds new + replaces content by slug", () => {
  const store = new Map()
  const a = mergeTier(store, [{ s: "w1", t: "W1", g: [], l: [], c: "c0" }])
  assert.deepEqual(a, ["w1"])
  assert.equal(store.get("w1").content, "c0")
  const b = mergeTier(store, [{ s: "w1", c: "c1-richer" }]) // delta
  assert.deepEqual(b, ["w1"])
  assert.equal(store.get("w1").content, "c1-richer")
  assert.equal(store.get("w1").title, "W1") // preserved
})

test("clampStop caps mobile at 1", () => {
  assert.equal(clampStop(3, true), 1)
  assert.equal(clampStop(3, false), 3)
  assert.equal(clampStop(-1, false), 0)
  assert.equal(clampStop(NaN, false), 0)
})

test("labels + hints exist for 4 stops", () => {
  assert.equal(STOP_LABELS.length, 4)
  assert.match(stopHint(2), /chapter|atom|passage/i)
})

test("mergeResults: flex first, fuzzy fills, deduped, capped", () => {
  assert.deepEqual(mergeResults(["a", "b"], ["b", "c", "d"], 3), ["a", "b", "c"])
})
