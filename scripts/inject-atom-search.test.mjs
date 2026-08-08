import { test } from "node:test"
import assert from "node:assert"
import { mergeAtoms } from "./inject-atom-search.mjs"

test("mergeAtoms adds atom entries keyed by frag, title carries parent work", () => {
  const idx = { "works/x": { title: "X", content: "hi", slug: "works/x" } }
  const atoms = { "testi/w#a1": { title: "A1", work: "W", text: "alpha beta" } }
  const out = mergeAtoms(idx, atoms)
  assert.equal(out["testi/w#a1"].title, "A1 — W")
  assert.equal(out["testi/w#a1"].content, "alpha beta")
  assert.equal(out["testi/w#a1"].slug, "testi/w#a1")
  assert.equal(out["works/x"].title, "X") // existing preserved
})

test("mergeAtoms leaves title bare when work is empty", () => {
  const idx = {}
  const atoms = { "testi/w#a2": { title: "A2", work: "", text: "gamma" } }
  const out = mergeAtoms(idx, atoms)
  assert.equal(out["testi/w#a2"].title, "A2")
})

test("mergeAtoms leaves title bare when work equals title", () => {
  const idx = {}
  const atoms = { "testi/w#a3": { title: "SameName", work: "SameName", text: "delta" } }
  const out = mergeAtoms(idx, atoms)
  assert.equal(out["testi/w#a3"].title, "SameName")
})
