// Pure helpers for the tiered depth search (searchDepth.inline.ts). Kept separate so
// they can be unit-tested without a DOM. Shard entries use compact keys to save bytes:
// s=slug t=title g=tags c=content. (`l`/links is dropped — the search client never reads
// it; the graph + backlinks read links from contentIndex.json instead.)

export type Entry = { s: string; t?: string; g?: string[]; l?: string[]; c: string }
export type Doc = {
  id: string
  slug: string
  title: string
  content: string
  tags: string[]
  links: string[]
}

export function entryToDoc(e: Entry): Doc {
  return {
    id: e.s,
    slug: e.s,
    title: e.t ?? "",
    content: e.c ?? "",
    tags: e.g ?? [],
    links: e.l ?? [],
  }
}

// Merge a tier's entries into the doc store: add new slugs, or REPLACE the content of
// existing ones (each tier's content is a superset of the shallower tier). Returns the
// slugs that must be (re)indexed in FlexSearch.
export function mergeTier(store: Map<string, Doc>, entries: Entry[]): string[] {
  const changed: string[] = []
  for (const e of entries) {
    const prev = store.get(e.s)
    if (prev) {
      prev.content = e.c ?? prev.content
      if (e.t !== undefined) prev.title = e.t
      if (e.g !== undefined) prev.tags = e.g
      if (e.l !== undefined) prev.links = e.l
    } else {
      store.set(e.s, entryToDoc(e))
    }
    changed.push(e.s)
  }
  return changed
}

export function clampStop(stop: number, isMobile: boolean): number {
  let s = Number.isFinite(stop) ? Math.floor(stop) : 0
  if (s < 0) s = 0
  if (s > 3) s = 3
  if (isMobile && s > 1) s = 1
  return s
}

export const STOP_LABELS = ["Fast", "Standard", "Deep", "Max"] as const

export function stopHint(stop: number): string {
  return [
    "Works & concepts — instant",
    "More terms per work — better recall",
    "Search inside chapters (atoms)",
    "Full depth + typo-tolerant (fuzzy)",
  ][clampStop(stop, false)]
}

// Insertion-ordered union: FlexSearch (exact/prefix) hits first, MiniSearch (fuzzy)
// fills the remainder. Deduped, capped at `limit`.
export function mergeResults(flexIds: string[], fuzzyIds: string[], limit: number): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const id of [...flexIds, ...fuzzyIds]) {
    if (!seen.has(id)) {
      seen.add(id)
      out.push(id)
    }
    if (out.length >= limit) break
  }
  return out
}

// Boolean query: "plato AND cave OR aristotle" → (plato ∧ cave) ∨ aristotle.
// Bare words without AND/OR follow `defaultOp` (OR = any term; AND = all terms).
export type BoolOp = "and" | "or"
export type BoolClause = { terms: string[] }
export type BoolQuery = { clauses: BoolClause[]; explicit: boolean }

export function parseBooleanQuery(raw: string, defaultOp: BoolOp = "or"): BoolQuery {
  const parts = String(raw || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  if (!parts.length) return { clauses: [], explicit: false }

  type Tok = { kind: "term" | "and" | "or"; v?: string }
  const toks: Tok[] = []
  let explicit = false
  for (const p of parts) {
    if (/^(AND|&&)$/i.test(p)) {
      toks.push({ kind: "and" })
      explicit = true
    } else if (/^(OR|\|\|)$/i.test(p)) {
      toks.push({ kind: "or" })
      explicit = true
    } else {
      toks.push({ kind: "term", v: p.toLowerCase() })
    }
  }

  const termsOnly = toks.filter((t) => t.kind === "term").map((t) => t.v!)
  if (!termsOnly.length) return { clauses: [], explicit }
  if (!explicit) {
    if (defaultOp === "and") return { clauses: [{ terms: termsOnly }], explicit: false }
    return { clauses: termsOnly.map((t) => ({ terms: [t] })), explicit: false }
  }

  const clauses: BoolClause[] = []
  let cur: string[] = []
  let pending: "and" | "or" | null = null
  const flush = () => {
    if (cur.length) {
      clauses.push({ terms: cur })
      cur = []
    }
  }
  for (const tok of toks) {
    if (tok.kind === "term") {
      if (pending === "or") flush()
      cur.push(tok.v!)
      pending = null
    } else {
      pending = tok.kind
    }
  }
  flush()
  return { clauses, explicit }
}

export function queryTerms(q: BoolQuery): string[] {
  return [...new Set(q.clauses.flatMap((c) => c.terms))]
}

export function haystackOf(d: { title?: string; content?: string; tags?: string[] }): string {
  return `${d.title || ""} ${d.content || ""} ${(d.tags || []).join(" ")}`.toLowerCase()
}

export function docMatchesBool(d: { title?: string; content?: string; tags?: string[] }, q: BoolQuery): boolean {
  if (!q.clauses.length) return false
  const hay = haystackOf(d)
  return q.clauses.some((cl) => cl.terms.every((t) => hay.includes(t)))
}

export function intersectIds(lists: string[][]): string[] {
  if (!lists.length) return []
  if (lists.length === 1) return [...new Set(lists[0])]
  const sets = lists.map((l) => new Set(l))
  return [...sets[0]].filter((id) => sets.every((s) => s.has(id)))
}

export function unionIds(lists: string[][]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const l of lists) {
    for (const id of l) {
      if (!seen.has(id)) {
        seen.add(id)
        out.push(id)
      }
    }
  }
  return out
}
