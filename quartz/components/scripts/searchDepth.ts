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

// Boolean query.
// Connectors (never search terms):  &  &&  AND   |  ||  OR   and parentheses.
// Lowercase "and"/"or" are ordinary words. Bare words without connectors
// follow `defaultOp` (OR = any term; AND = all terms).
// AND binds tighter than OR. Example: (sea & shore) | dog
export type BoolOp = "and" | "or"
export type BoolTerm = { v: string; exact: boolean }
export type BoolClause = { terms: BoolTerm[] }
export type BoolQuery = { clauses: BoolClause[]; explicit: boolean }

type BTok =
  | { kind: "term"; v: string; exact: boolean }
  | { kind: "and" }
  | { kind: "or" }
  | { kind: "lp" }
  | { kind: "rp" }

type BAst =
  | { k: "term"; v: string; exact: boolean }
  | { k: "and" | "or"; l: BAst; r: BAst }

function tokenizeBool(raw: string): BTok[] {
  const s = String(raw || "")
  const out: BTok[] = []
  let i = 0
  const pushTerm = (t: string, exact: boolean) => {
    if (t) out.push({ kind: "term", v: t.toLowerCase(), exact })
  }
  while (i < s.length) {
    const c = s[i]
    if (/\s/.test(c)) {
      i++
      continue
    }
    if (c === '"' || c === "\u201c" || c === "\u201d") {
      const open = c
      const close =
        open === "\u201c" ? "\u201d" : open === "\u201d" ? "\u201d" : open
      i++
      let j = i
      while (j < s.length && s[j] !== close && s[j] !== '"') j++
      pushTerm(s.slice(i, j).trim(), true)
      i = j < s.length ? j + 1 : j
      continue
    }
    if (c === "(") {
      out.push({ kind: "lp" })
      i++
      continue
    }
    if (c === ")") {
      out.push({ kind: "rp" })
      i++
      continue
    }
    if (c === "&") {
      out.push({ kind: "and" })
      i += s[i + 1] === "&" ? 2 : 1
      continue
    }
    if (c === "|") {
      out.push({ kind: "or" })
      i += s[i + 1] === "|" ? 2 : 1
      continue
    }
    let j = i
    while (
      j < s.length &&
      !/\s/.test(s[j]) &&
      s[j] !== "(" &&
      s[j] !== ")" &&
      s[j] !== "&" &&
      s[j] !== "|" &&
      s[j] !== '"'
    )
      j++
    const w = s.slice(i, j)
    i = j
    if (w === "AND") out.push({ kind: "and" })
    else if (w === "OR") out.push({ kind: "or" })
    else pushTerm(w, false)
  }
  return out
}

function termKey(t: BoolTerm): string {
  return (t.exact ? "1:" : "0:") + t.v
}

function astToDnf(ast: BAst): BoolTerm[][] {
  if (ast.k === "term") return [[{ v: ast.v, exact: ast.exact }]]
  const L = astToDnf(ast.l)
  const R = astToDnf(ast.r)
  if (ast.k === "or") return [...L, ...R]
  const out: BoolTerm[][] = []
  for (const a of L) for (const b of R) out.push([...a, ...b])
  return out
}

function dedupeTerms(cl: BoolTerm[]): BoolTerm[] {
  const seen = new Set<string>()
  const out: BoolTerm[] = []
  for (const t of cl) {
    const k = termKey(t)
    if (seen.has(k)) continue
    seen.add(k)
    out.push(t)
  }
  return out
}

export function parseBooleanQuery(raw: string, defaultOp: BoolOp = "or"): BoolQuery {
  const toks = tokenizeBool(raw)
  if (!toks.length) return { clauses: [], explicit: false }

  const explicit = toks.some((t) => t.kind !== "term")
  const termsOnly = toks.filter((t): t is Extract<BTok, { kind: "term" }> => t.kind === "term")
  if (!termsOnly.length) return { clauses: [], explicit }
  if (!explicit) {
    const terms = termsOnly.map((t) => ({ v: t.v, exact: t.exact }))
    if (defaultOp === "and") return { clauses: [{ terms }], explicit: false }
    return { clauses: terms.map((t) => ({ terms: [t] })), explicit: false }
  }

  let pos = 0
  const peek = () => toks[pos]
  const eat = (k?: BTok["kind"]) => {
    const t = toks[pos]
    if (!t || (k && t.kind !== k)) return null
    pos++
    return t
  }

  const parseOr = (): BAst | null => {
    let left = parseAnd()
    if (!left) return null
    while (peek()?.kind === "or") {
      eat()
      const right = parseAnd()
      if (!right) break
      left = { k: "or", l: left, r: right }
    }
    return left
  }
  const parseAnd = (): BAst | null => {
    let left = parsePrimary()
    if (!left) return null
    while (true) {
      const n = peek()
      if (!n || n.kind === "or" || n.kind === "rp") break
      if (n.kind === "and") eat()
      const right = parsePrimary()
      if (!right) break
      left = { k: "and", l: left, r: right }
    }
    return left
  }
  const parsePrimary = (): BAst | null => {
    const n = peek()
    if (!n) return null
    if (n.kind === "lp") {
      eat()
      const inner = parseOr()
      eat("rp")
      return inner
    }
    if (n.kind === "term") {
      eat()
      return { k: "term", v: n.v, exact: n.exact }
    }
    eat()
    return parsePrimary()
  }

  const ast = parseOr()
  if (!ast) return { clauses: [], explicit }
  const dnf = astToDnf(ast)
    .map(dedupeTerms)
    .filter((cl) => cl.length)
  return { clauses: dnf.map((terms) => ({ terms })), explicit }
}

export function queryTerms(q: BoolQuery): string[] {
  return [...new Set(q.clauses.flatMap((c) => c.terms.map((t) => t.v)))]
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

export function termInHay(hay: string, t: BoolTerm): boolean {
  if (!t.v) return true
  if (!t.exact) return hay.includes(t.v)
  const re = new RegExp(`(?<![\\p{L}\\p{N}_])${escapeRe(t.v)}(?![\\p{L}\\p{N}_])`, "iu")
  return re.test(hay)
}

export function haystackOf(d: { title?: string; content?: string; tags?: string[] }): string {
  return `${d.title || ""} ${d.content || ""} ${(d.tags || []).join(" ")}`.toLowerCase()
}

export function hayMatchesQuery(hay: string, raw: string, defaultOp: BoolOp = "and"): boolean {
  const q = String(raw || "").trim()
  if (!q) return true
  const parsed = parseBooleanQuery(q, defaultOp)
  if (!parsed.clauses.length) return false
  const h = hay.toLowerCase()
  return parsed.clauses.some((cl) => cl.terms.every((t) => termInHay(h, t)))
}

export function fieldsMatchQuery(fields: Array<string | undefined | null>, raw: string, defaultOp: BoolOp = "and"): boolean {
  return hayMatchesQuery(fields.map((f) => String(f || "")).join(" \n "), raw, defaultOp)
}

export function docMatchesBool(d: { title?: string; content?: string; tags?: string[] }, q: BoolQuery): boolean {
  if (!q.clauses.length) return false
  const hay = haystackOf(d)
  return q.clauses.some((cl) => cl.terms.every((t) => termInHay(hay, t)))
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
