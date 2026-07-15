// Preprocess the Obsidian "Knowledge Graph" (Philosophy) vault into Quartz content.
// Mirrors ../English/quartz-eng-lit/preprocess.mjs's proven architecture and tricks
// (SPA atom-split reading pages, lenient frontmatter parsing, dead-link-safe wikilink
// rewriting) but the philosophy vault is structurally simpler: each work's atoms are
// a FLAT ordered sequence (no chapter/scene/part nesting), and there is no EN/IT
// bilingual toggle — atoms stay in their source language, with only IT/EN *summaries*
// as searchable metadata.
//
// - copies the 187 Knowledge Graph aggregator notes into ./content (lowercased type
//   folders), rewriting [[wikilinks]] to either another node id or a work basename
// - emits ONE SPA reading page per work (testi/<philosopher>/<work>.md) with every
//   atom inline behind an <span class="atom-split"> marker (Cloudflare Pages file-
//   count cap: ~9320 atoms as individual pages would blow the ~20k limit)
// - builds ./quartz/static/index.json (one record per work) and taxonomy.json (the
//   controlled vocabulary + live work_count) consumed by the client-side tables/search
// - generates index.md, opere.md, assi.md, cerca.md, 404.md (thin shells; the client
//   renders tables/facets from the JSON — English's core scaling trick)
import { promises as fs } from "node:fs"
import { existsSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

// SPA=1 is MANDATORY: 9320 atoms as individual pages would blow Cloudflare Pages'
// ~20k-file cap. There is no "classic" per-atom fallback here (unlike English, which
// kept one for its richer chapter/scene hierarchy) — philosophy atoms are flat, so a
// per-atom page mode would have no benefit and only risk the file-count cap.
const SPA = process.env.SPA === "1"
if (!SPA) {
  console.error(
    "preprocess.mjs requires SPA=1 (Cloudflare Pages file-count cap). Run: SPA=1 node preprocess.mjs",
  )
  process.exit(1)
}

// ---- paths, resolved relative to this script (never hardcoded absolute) ----------
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url))
const ROOT = SCRIPT_DIR // quartz-philosophy/
const REPO_ROOT = path.resolve(ROOT, "..") // Philosophy/
const VAULT = path.join(REPO_ROOT, "VaultPhilosophy")
const KG_DIR = path.join(VAULT, "Knowledge Graph")
const PHIL_DIR = path.join(VAULT, "Philosophers")
const DATA_DIR = path.join(REPO_ROOT, "data")
const CONTENT = path.join(ROOT, "content")
const STATIC_DIR = path.join(ROOT, "quartz", "static")
const TESTI_REL = "testi"

// Knowledge Graph folder name -> taxonomy.json type key, and back. Content paths use
// the lowercased plural (axes/positions/concepts/arguments/figures/forms/schools).
const FOLDER_TO_TYPE = {
  Axes: "axis",
  Positions: "position",
  Concepts: "concept",
  Arguments: "argument",
  Figures: "figure",
  Forms: "form",
  Schools: "school",
}
const TYPE_TO_OUT = {
  axis: "axes",
  position: "positions",
  concept: "concepts",
  argument: "arguments",
  figure: "figures",
  form: "forms",
  school: "schools",
}
const TAX_KEY_TO_TYPE = {
  axes: "axis",
  positions: "position",
  concepts: "concept",
  arguments: "argument",
  figures: "figure",
  forms: "form",
  schools: "school",
}

// ---- tiny self-contained frontmatter parse/stringify (no node_modules needed) ----
// The vault's frontmatter is machine-generated, clean YAML (quoted strings, block-
// list arrays, bare numbers) — much more regular than English's hand-authored vault,
// so a lenient line-based parser (same approach as English's parseFrontmatter) is
// both sufficient and dependency-free, which matters since preprocess must run before
// `npm install` in the build order.
function parseFrontmatter(raw) {
  const m = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/)
  if (!m) return { data: {}, content: raw }
  const data = {}
  const lines = m[1].split(/\r?\n/)
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const kv = line.match(/^(\w[\w.-]*):\s?(.*)$/)
    if (!kv) {
      i++
      continue
    }
    const key = kv[1]
    let v = kv[2].trim()
    if (v === "") {
      // possible block list ("aliases:\n  - \"a\"\n  - \"b\"")
      const arr = []
      let j = i + 1
      while (j < lines.length && /^\s+-\s+/.test(lines[j])) {
        arr.push(lines[j].replace(/^\s+-\s+/, "").trim().replace(/^["']|["']$/g, ""))
        j++
      }
      data[key] = arr
      i = j
      continue
    }
    if (v.startsWith("[") && v.endsWith("]")) {
      data[key] = v
        .slice(1, -1)
        .split(",")
        .map((x) => x.trim().replace(/^["']|["']$/g, ""))
        .filter(Boolean)
    } else if (/^-?\d+(\.\d+)?$/.test(v)) {
      data[key] = Number(v)
    } else if (v === "true" || v === "false") {
      data[key] = v === "true"
    } else if (v === "null" || v === "~") {
      data[key] = null
    } else {
      if (
        (v.startsWith('"') && v.endsWith('"') && v.length > 1) ||
        (v.startsWith("'") && v.endsWith("'") && v.length > 1)
      ) {
        v = v.slice(1, -1)
      }
      data[key] = v
    }
    i++
  }
  return { data, content: m[2] }
}
function yamlScalar(v) {
  if (v === null || v === undefined) return "null"
  if (typeof v === "number" || typeof v === "boolean") return String(v)
  return JSON.stringify(String(v)) // double-quoted YAML scalar == JSON string for our alphabet
}
function stringifyFrontmatter(data) {
  const lines = []
  for (const [k, v] of Object.entries(data)) {
    if (v === undefined) continue
    if (Array.isArray(v)) {
      if (!v.length) {
        lines.push(`${k}: []`)
        continue
      }
      lines.push(`${k}:`)
      for (const item of v) lines.push(`  - ${yamlScalar(item)}`)
    } else {
      lines.push(`${k}: ${yamlScalar(v)}`)
    }
  }
  return `---\n${lines.join("\n")}\n---\n\n`
}
function compose(content, data) {
  return stringifyFrontmatter(data) + content
}

// ---- misc helpers (ported from English) -------------------------------------------
function sluggify(s) {
  return s
    .split("/")
    .map((seg) =>
      seg
        .replace(/\s/g, "-")
        .replace(/&/g, "-and-")
        .replace(/%/g, "-percent")
        .replace(/\?/g, "")
        .replace(/#/g, "")
        .toLowerCase(),
    )
    .join("/")
    .replace(/\/$/, "")
}
function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    c === "&" ? "&amp;" : c === "<" ? "&lt;" : c === ">" ? "&gt;" : "&quot;",
  )
}
function prettify(basename) {
  return String(basename).replace(/_/g, " ").trim()
}

// ---- full-text search index (TF-IDF keywords per work) ----------------------------
// Mirrors ../English/quartz-eng-lit/preprocess.mjs's keywordCounts/topTfIdf (that repo
// does not rely on Quartz's own contentIndex.json, which truncates every page's
// indexed text to ~500 chars — useless for full-text recall inside a 200k-word work).
// English only: the corpus is ~99% English prose with pockets of Latin (Seneca's
// tragedies, Lucretius). We do NOT special-case lang — every work's `lang` field in
// this vault is "en" even when the body is pure Latin (verified against the Seneca
// atoms), so it cannot drive a strip/don't-strip branch. In practice this is harmless:
// English function words ("the", "and", "of", "is") essentially never occur in Latin
// text, so filtering them out of a Latin work is close to a no-op — the Latin content
// words survive untouched and dominate the TF-IDF ranking.
const STOPWORDS = new Set((
  "a about an and are as at be been but by can did do does each for from had has have he her here him his how i if in into is it its no not of on one or our so that the their them then there these they this to too two up was we were what when where which who will with you your"
).split(/\s+/).filter(Boolean))

// Per-work term frequencies (Map<word,count>) computed over the full concatenated
// atom text (the same body text the SPA reading page renders — no second vault read).
function keywordCounts(content) {
  const cleaned = content
    .replace(/\[\[(?:[^\]|]+\|)?([^\]]+)\]\]/g, " $1 ") // keep wikilink label
    .replace(/\[[^\]]*\]\([^)]*\)/g, " ") // md links
    .replace(/[`*_>#|]/g, " ") // md syntax
    .toLowerCase()
    .replace(/[^a-zà-ÿ\s]/g, " ") // letters only
  const counts = new Map()
  for (const w of cleaned.split(/\s+/)) {
    if (w.length < 3 || STOPWORDS.has(w)) continue
    counts.set(w, (counts.get(w) || 0) + 1)
  }
  return counts
}

// Rank each work's terms by TF-IDF across the 115-work corpus and keep the top-N
// (most discriminating first) as an array — this becomes the record's `kw` field.
function topTfIdf(countsByKey, N = 40) {
  const df = new Map()
  for (const counts of Object.values(countsByKey))
    for (const w of counts.keys()) df.set(w, (df.get(w) || 0) + 1)
  const total = Object.keys(countsByKey).length || 1
  const out = {}
  for (const [key, counts] of Object.entries(countsByKey)) {
    if (!counts.size) {
      out[key] = []
      continue
    }
    const scored = []
    for (const [w, c] of counts) {
      const idf = Math.log(total / (df.get(w) || 1))
      if (idf <= 0) continue
      scored.push([w, c * idf])
    }
    scored.sort((a, b) => b[1] - a[1])
    out[key] = scored.slice(0, N).map((x) => x[0])
  }
  return out
}
function countWords(s) {
  const m = String(s)
    .replace(/<[^>]+>/g, " ")
    .match(/\S+/g)
  return m ? m.length : 0
}
async function walkMd(dir) {
  const out = []
  async function rec(d) {
    let ents
    try {
      ents = await fs.readdir(d, { withFileTypes: true })
    } catch {
      return
    }
    for (const ent of ents) {
      const full = path.join(d, ent.name)
      if (ent.isDirectory()) await rec(full)
      else if (ent.name.endsWith(".md")) out.push(full)
    }
  }
  await rec(dir)
  return out
}
// Strip the first body H1 line if it matches `title` (after trim). Quartz renders the
// frontmatter `title` as the page heading automatically; leaving a duplicate body H1
// produces a double title.
function stripLeadingH1(content, title) {
  if (!title) return content
  const norm = String(title).trim()
  return content.replace(/^([ \t]*\r?\n)*[ \t]*#[ \t]+(.+?)[ \t]*\r?\n/, (match, _b, h1) =>
    h1.trim() === norm ? "" : match,
  )
}

async function main() {
  // ---- wipe generated output -------------------------------------------------
  await fs.rm(CONTENT, { recursive: true, force: true })
  await fs.mkdir(CONTENT, { recursive: true })
  await fs.mkdir(STATIC_DIR, { recursive: true })
  // quartz/static/*.json is entirely generated (index.json, taxonomy.json — and any
  // stale leftovers from an earlier scaffold copy); wipe every top-level .json so a
  // re-run never ships data from a different vault.
  for (const f of await fs.readdir(STATIC_DIR)) {
    if (f.endsWith(".json")) await fs.rm(path.join(STATIC_DIR, f), { force: true })
  }

  // ---- load the controlled vocabulary (data/taxonomy.json) -------------------
  const taxRaw = JSON.parse(await fs.readFile(path.join(DATA_DIR, "taxonomy.json"), "utf8"))
  const idInfo = new Map() // id -> {type,label_it,label_en,aliases,...rest}
  for (const [taxKey, type] of Object.entries(TAX_KEY_TO_TYPE)) {
    for (const node of taxRaw[taxKey] || []) idInfo.set(node.id, { ...node, type })
  }
  const idHref = new Map() // id -> "<typefolder>/<id>"
  for (const [id, info] of idInfo) idHref.set(id, `${TYPE_TO_OUT[info.type]}/${id}`)

  // ---- load per-work tags (data/tags/<Philosopher>.json) + live work_count ---
  const tagsDir = path.join(DATA_DIR, "tags")
  const tagsByPhil = new Map() // philosopher (folder-cased) -> Map<workKey, tagsObj>
  const liveWorkCount = new Map() // taxonomy id -> number of works tagged with it
  for (const f of await fs.readdir(tagsDir)) {
    if (!f.endsWith(".json")) continue
    const philosopher = f.replace(/\.json$/, "")
    const obj = JSON.parse(await fs.readFile(path.join(tagsDir, f), "utf8"))
    const m = new Map(Object.entries(obj))
    tagsByPhil.set(philosopher, m)
    for (const tags of m.values()) {
      for (const field of ["axes", "positions", "concepts", "arguments", "figures", "forms", "schools"]) {
        for (const id of tags[field] || []) liveWorkCount.set(id, (liveWorkCount.get(id) || 0) + 1)
      }
    }
  }

  // ---- Philosophers/<Name>/_raw/*.md: per-work publication metadata ----------
  const philosophers = (await fs.readdir(PHIL_DIR, { withFileTypes: true }))
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .sort()
  const rawMeta = new Map() // workKey (basename, canonical) -> {data, philosopher}
  for (const philosopher of philosophers) {
    const rawDir = path.join(PHIL_DIR, philosopher, "_raw")
    if (!existsSync(rawDir)) continue
    for (const f of await fs.readdir(rawDir)) {
      if (!f.endsWith(".md")) continue
      const workKey = f.replace(/\.md$/, "")
      const raw = await fs.readFile(path.join(rawDir, f), "utf8")
      const { data } = parseFrontmatter(raw)
      rawMeta.set(workKey, { ...data, philosopher: data.philosopher || philosopher })
    }
  }

  // ---- Philosophers/<Name>/Atomized/<WORK>/NNN_slug.md: atoms, flat & ordered -
  // GOTCHA: on Windows, long Atomized/<WORK> directory names get silently truncated
  // (MAX_PATH mitigation baked into the atomizer — see vault git log). The directory
  // name is therefore NOT a reliable work key. Every atom's frontmatter carries the
  // untruncated canonical key in `work:`, matching the _raw basename exactly — group
  // atoms by that field, never by the (possibly-truncated) directory name.
  const workAtoms = new Map() // canonical workKey -> { philosopher, atoms: [{data,body,itBody}] }
  let truncatedDirs = 0
  let itAtoms = 0
  for (const philosopher of philosophers) {
    const atomizedDir = path.join(PHIL_DIR, philosopher, "Atomized")
    if (!existsSync(atomizedDir)) continue
    const files = await walkMd(atomizedDir)
    for (const f of files) {
      // `<atom>.it.md` is the translation sibling, not an atom of its own: it is
      // paired onto its source below. Walking it as an atom would publish the
      // Italian twice and give it a bogus atom_n.
      if (f.endsWith(".it.md")) continue
      const raw = await fs.readFile(f, "utf8")
      const { data, content } = parseFrontmatter(raw)
      const dirKey = path.basename(path.dirname(f))
      const workKey = data.work || dirKey
      if (data.work && data.work !== dirKey) truncatedDirs++
      if (!workAtoms.has(workKey))
        workAtoms.set(workKey, { philosopher: data.philosopher || philosopher, atoms: [] })

      // Pair the translation by filename. Unlike English — where one prose block
      // recurs across fragment, chapter and full-work pages, forcing a
      // content-addressed sha(en)->it cache — an atom appears exactly once in its
      // work's SPA page, so the sibling file IS the translation. No block matching,
      // hence no block-count mismatch silently dropping a whole page.
      let itBody = null
      const itPath = f.slice(0, -3) + ".it.md"
      if (existsSync(itPath)) {
        itBody = parseFrontmatter(await fs.readFile(itPath, "utf8")).content
        itAtoms++
      }
      workAtoms.get(workKey).atoms.push({ data, body: content, itBody })
    }
  }
  for (const w of workAtoms.values())
    w.atoms.sort((a, b) => (a.data.atom_n ?? 0) - (b.data.atom_n ?? 0))
  if (truncatedDirs) console.log(`note: ${truncatedDirs} atoms live under a truncated directory name (resolved via frontmatter "work:")`)
  console.log(`traduzioni: ${itAtoms} atomi con sibling .it.md`)
  // Stampato dopo il loop delle opere, piu' sotto: vedi abstractsEmitted.

  // Un titolo che si APRE dichiarando traduttore/editore come autore: e' il suo
  // testo, non quello del filosofo. L'ancora `^` e' cio' che distingue
  // "TRANSLATOR'S PREFACE" (apparato) da "PREFACE" (Hume) e da "II. Refutation
  // of the Counterfeiter's pretended Right against the Editor" (Kant).
  // L'apostrofo puo' essere dritto o tipografico a seconda dell'edizione.
  const APPARATUS_TITLE =
    /^\s*(the\s+)?(translator|editor)['’]?s?\s+(preface|introduction|note)\b|^\s*editorial\s+notices\b|^\s*note\s+by\s+the\s+editor\b/i
  const isApparatusTitle = (t) => APPARATUS_TITLE.test(String(t || ""))
  let apparatusSkipped = 0
  let abstractsEmitted = 0

  const LANG_NAME = {
    en: "inglese",
    de: "tedesco",
    fr: "francese",
    es: "spagnolo",
    la: "latino",
    it: "italiano",
    grc: "greco",
  }

  // La riga di provenienza dell'opera. Ritorna "" se non c'e' niente da citare:
  // meglio nessuna riga che una riga vuota di promesse.
  function sourceLine({ traduttore, edizione, anno_edizione, lang }) {
    const ed = [edizione, anno_edizione].filter(Boolean).join(", ")
    const bits = []
    if (traduttore) {
      // "chi ha tradotto" prima di "chi ha stampato": e' il traduttore a
      // detenere il diritto sulla traduzione, ed e' lui che stiamo citando.
      bits.push(`Traduzione di ${traduttore}`)
      if (ed) bits.push(ed)
    } else {
      const name = LANG_NAME[String(lang || "").toLowerCase()]
      if (name) bits.push(`Testo originale ${name}`)
      if (ed) bits.push(ed)
    }
    if (!bits.length) return ""
    bits.push("pubblico dominio")
    return `<p class="work-source">${esc(bits.join(" · "))}</p>`
  }

  // ---- emit SPA reading pages (testi/<philosopher>/<work>.md) ----------------
  const works = [] // index.json records
  const workHrefByKey = new Map() // canonical workKey -> { href, title } (for KG-note link rewriting)
  const kwCountsByHref = {} // workHref -> Map<word,count> over the full concatenated atom text
  let workPages = 0

  for (const [workKey, { philosopher, atoms: allAtoms }] of workAtoms) {
    // Gli apparati editoriali non si pubblicano. Prefazioni, introduzioni e note
    // del *traduttore* o dell'*editore* sono commento sull'opera, non l'opera.
    //
    // L'ancora a inizio titolo non e' un dettaglio: "PREFACE" e "INTRODUCTION"
    // nudi NON sono apparato — la Prefazione all'Abstract e' di Hume,
    // l'Introduzione all'Estetica e' di Hegel — e "II. Refutation of the
    // Counterfeiter's pretended Right against the Editor" e' Kant che discute
    // dell'editore-stampatore. Solo un titolo che *si apre* dichiarando il
    // traduttore o l'editore come autore e' apparato.
    const atoms = allAtoms.filter((a) => !isApparatusTitle(a.data.atom_title))
    apparatusSkipped += allAtoms.length - atoms.length
    if (!atoms.length) continue
    const meta = rawMeta.get(workKey) || {}
    const first = atoms[0].data
    const philosopherName = meta.philosopher || philosopher
    const philLower = String(philosopherName).toLowerCase()
    const workSlug = sluggify(`${TESTI_REL}/${philLower}/${workKey}`)
    const title = (meta.title && String(meta.title).trim()) || prettify(workKey)
    const lang = meta.lang ?? first.lang ?? ""
    const edizione = meta.edizione ?? first.edizione ?? ""
    const traduttore = meta.traduttore ?? first.traduttore ?? ""
    const anno_edizione = meta.anno_edizione ?? first.anno_edizione ?? null
    const pd_year = meta.pd_year ?? first.pd_year ?? null
    const kind = meta.kind || "work"

    const tagsMap = tagsByPhil.get(philosopherName)
    const tags = (tagsMap && tagsMap.get(workKey)) || {}

    // group atoms by atom_title for local numbering (multiple atoms can share one
    // section title — the atomizer splits long sections at paragraph boundaries) and
    // chapter grouping in the reader's TOC.
    const titleGroups = new Map()
    for (const a of atoms) {
      const t = a.data.atom_title || ""
      if (!titleGroups.has(t)) titleGroups.set(t, [])
      titleGroups.get(t).push(a)
    }

    let totalWords = 0
    const blocks = []
    const kwTextParts = [] // full atom body text, reused for keyword extraction below
    for (let i = 0; i < atoms.length; i++) {
      const a = atoms[i]
      const atomN = a.data.atom_n ?? i + 1
      const atomId = String(atomN).padStart(3, "0")
      const atomTitleRaw = String(a.data.atom_title || "").trim()
      const isFlat = atomTitleRaw === "" || atomTitleRaw.toLowerCase() === "(intero)"
      const isIntro = i === 0
      const chapter = isFlat ? "" : atomTitleRaw
      const group = titleGroups.get(a.data.atom_title || "") || []
      let label
      if (isIntro) label = title
      else if (isFlat) label = `Parte ${atomN}`
      else if (group.length > 1) label = `${atomTitleRaw} (${group.indexOf(a) + 1}/${group.length})`
      else label = atomTitleRaw

      const H1_RE = /^([ \t]*\r?\n)*[ \t]*#[ \t]+(.+?)[ \t]*\r?\n/

      let body = a.body
      // drop the leading "# <atom_title>" H1 (data-title carries it; avoids a
      // duplicate heading inside the reading pane)
      const h1m = body.match(H1_RE)
      const droppedH1 = Boolean(h1m && (!atomTitleRaw || h1m[2].trim() === atomTitleRaw))
      if (droppedH1) body = body.slice(h1m[0].length)
      // scripts/link/run.py ha scritto i wikilink nel vault (dove servono al
      // grafo di Obsidian); qui diventano link del sito. Gli atomi puntano solo
      // a id del vocabolario, che `idHref` conosce gia' tutti: `workHrefByKey`,
      // ancora incompleto a questo punto del ciclo, non viene interrogato.
      body = rewriteLinks(body)
      body = body.trim()
      totalWords += countWords(body)
      // EN only: the word count measures the work, and mixing Italian into the
      // TF-IDF sample would let translation artefacts outrank the source's terms.
      kwTextParts.push(body)

      let itBody = a.itBody
      if (itBody) {
        // Mirror the source's H1 handling rather than re-testing the title: the
        // Italian H1 is translated, so it never equals atom_title and a repeat of
        // the EN test would always keep it — leaving a heading on the IT side that
        // the EN side doesn't have.
        if (droppedH1) itBody = itBody.replace(H1_RE, "")
        itBody = rewriteLinks(itBody)
        itBody = itBody.trim()
      }

      blocks.push(
        `\n\n<span class="atom-split" data-atom="${esc(atomId)}" data-title="${esc(label)}" data-chapter="${esc(chapter)}" data-kind="${isIntro ? "intro" : "atom"}"></span>\n\n` +
          body +
          // atomRouter partitions on this marker and only shows the .ar-lang
          // switch when at least one atom carries an IT half.
          (itBody
            ? `\n\n<span class="qlang-split" data-lang="it"></span>\n\n` + itBody
            : ""),
      )
    }

    const fmData = {}
    for (const [k, v] of Object.entries({
      title,
      philosopher: philosopherName,
      lang,
      edizione,
      traduttore,
      anno_edizione,
      pd_year,
      kind,
    })) {
      if (v !== undefined && v !== null && v !== "") fmData[k] = v
    }
    fmData.tags = ["graph/work", `philosopher/${philLower}`]

    const mount = `<div class="atom-reader" data-work="${esc(workSlug)}" data-philosopher="${esc(philosopherName)}"></div>\n`
    // L'abstract in testa all'opera. Vive gia' in data/tags/<Filosofo>.json, ma
    // finora finiva solo in index.json — cioe' lo vedevano la tabella e la
    // ricerca, e mai il lettore che apriva l'opera.
    //
    // Sta PRIMA del mount di proposito: atomRouter parte dal primo marker
    // atom-split e ignora i nodi che lo precedono (in partition() `cur` e'
    // ancora null), quindi il callout resta in pagina e non viene inghiottito
    // dal lettore ne' contato come atomo.
    //
    // In inglese: e' la lingua franca del corpus, e per Nietzsche o Ortega e'
    // l'unico modo di far capire di cosa parla l'opera a chi non legge il
    // tedesco o lo spagnolo.
    const abstract = String(tags.summary_en || "").trim()
    const abstractBlock = abstract
      ? `> [!abstract]\n> ${abstract.replace(/\s*\n\s*/g, " ")}\n\n`
      : ""

    // La provenienza, in chiaro sotto il titolo. I campi c'erano gia' nel
    // frontmatter ma non li leggeva nessuno: nel markdown emesso restavano
    // metadati, non una citazione.
    //
    // Serve a due cose diverse. Dove pubblichiamo una traduzione di pubblico
    // dominio, il traduttore e' l'autore di QUELLE parole e va citato: e' un
    // credito dovuto, non un dettaglio bibliografico. Dove pubblichiamo
    // l'originale (Nietzsche in tedesco, Descartes in francese), dirlo spiega al
    // lettore perche' la pagina non e' in inglese — e ricorda perche' la fonte e'
    // stata scelta cosi': senza traduttore nella catena non c'e' nessun diritto
    // altrui in mezzo.
    const provenance = sourceLine({ traduttore, edizione, anno_edizione, lang })
    const provenanceBlock = provenance ? `${provenance}\n\n` : ""

    const dest = path.join(CONTENT, (workSlug + ".md").split("/").join(path.sep))
    await fs.mkdir(path.dirname(dest), { recursive: true })
    await fs.writeFile(
      dest,
      compose(abstractBlock + provenanceBlock + mount + blocks.join(""), fmData),
    )
    workPages++
    if (abstract) abstractsEmitted++

    workHrefByKey.set(workKey, { href: workSlug, title })
    kwCountsByHref[workSlug] = keywordCounts(kwTextParts.join("\n\n"))

    works.push({
      href: workSlug,
      title,
      philosopher: philosopherName,
      lang,
      kind,
      words: totalWords,
      atoms: atoms.length,
      edizione: edizione || "",
      traduttore: traduttore || "",
      pd_year: pd_year ?? null,
      summary_it: tags.summary_it || "",
      summary_en: tags.summary_en || "",
      axes: tags.axes || [],
      positions: tags.positions || [],
      concepts: tags.concepts || [],
      arguments: tags.arguments || [],
      figures: tags.figures || [],
      forms: tags.forms || [],
      schools: tags.schools || [],
    })
  }
  works.sort((a, b) => (a.philosopher + a.title).localeCompare(b.philosopher + b.title))

  // ---- TF-IDF keywords per work (full-text search recall; see keywordCounts) ----
  const kwArrays = topTfIdf(kwCountsByHref, 40)
  for (const w of works) w.kw = kwArrays[w.href] || []

  // ---- rewrite [[wikilinks]] in Knowledge Graph note bodies ------------------
  // A wikilink target is either another node id (axis/position/concept/argument/
  // figure/form/school) or a work basename (the "## Opere" lists). Anything that
  // resolves to neither falls back to plain label text — never a dead link.
  function rewriteLinks(content) {
    return content.replace(/\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]/g, (_m, target, label) => {
      const t = target.trim()
      const lbl = label ? label.trim() : null
      const w = workHrefByKey.get(t)
      if (w) return `[${lbl || w.title}](/${w.href})`
      if (idHref.has(t)) {
        const info = idInfo.get(t)
        return `[${lbl || (info ? info.label_it : t)}](/${idHref.get(t)})`
      }
      return lbl || t
    })
  }

  // ---- emit the 187 aggregator notes (axes/positions/concepts/arguments/figures/forms/schools) ----
  const kgFiles = await walkMd(KG_DIR)
  let kgWritten = 0
  for (const f of kgFiles) {
    const rel = path.relative(KG_DIR, f).split(path.sep).join("/")
    const typeFolder = rel.split("/")[0]
    const type = FOLDER_TO_TYPE[typeFolder]
    if (!type) continue // unknown top-level folder — skip defensively
    const raw = await fs.readFile(f, "utf8")
    const { data, content } = parseFrontmatter(raw)
    const id = data.id || path.basename(f, ".md")
    const newData = { ...data, work_count: liveWorkCount.get(id) || 0, title: data.label_it || id }
    let newContent = rewriteLinks(content)
    newContent = stripLeadingH1(newContent, data.label_it)
    const outRel = `${TYPE_TO_OUT[type]}/${id}.md`
    const dest = path.join(CONTENT, outRel.split("/").join(path.sep))
    await fs.mkdir(path.dirname(dest), { recursive: true })
    await fs.writeFile(dest, compose(newContent, newData))
    kgWritten++
  }

  // ---- quartz/static/index.json + taxonomy.json ------------------------------
  await fs.writeFile(path.join(STATIC_DIR, "index.json"), JSON.stringify(works))

  // ---- quartz/static/index_kw.json: inverted index {term: [workHref, ...]} ------
  // Lets the client resolve a term without scanning every record. Covers two
  // sources so a lookup stays language-agnostic:
  //  1. each work's own `kw` (full-text TF-IDF terms, language of the source text)
  //  2. the label_it / label_en / aliases of every taxonomy node the work is tagged
  //     with — so an English query ("empiricism") reaches a work only tagged via
  //     its Italian label or a German/Latin passage, and vice versa. This is an
  //     addition on top of the existing canonical-id fields, not a replacement.
  const kwIndex = {} // term -> Set<href>
  function addKwTerm(term, href) {
    const t = String(term || "").trim().toLowerCase()
    if (!t) return
    if (!kwIndex[t]) kwIndex[t] = new Set()
    kwIndex[t].add(href)
  }
  for (const w of works) {
    for (const term of w.kw) addKwTerm(term, w.href)
    for (const field of ["axes", "positions", "concepts", "arguments", "figures", "forms", "schools"]) {
      for (const id of w[field] || []) {
        const info = idInfo.get(id)
        if (!info) continue
        for (const lbl of [info.label_it, info.label_en, ...(info.aliases || [])]) {
          if (!lbl) continue
          addKwTerm(lbl, w.href) // whole phrase, exact-match lookups
          for (const word of String(lbl).toLowerCase().split(/[^a-zà-ÿ]+/)) {
            if (word.length >= 3 && !STOPWORDS.has(word)) addKwTerm(word, w.href)
          }
        }
      }
    }
  }
  const kwOut = {}
  for (const [term, hrefs] of Object.entries(kwIndex)) kwOut[term] = [...hrefs]
  await fs.writeFile(path.join(STATIC_DIR, "index_kw.json"), JSON.stringify(kwOut))

  const taxOut = {}
  for (const [taxKey, type] of Object.entries(TAX_KEY_TO_TYPE)) {
    taxOut[taxKey] = (taxRaw[taxKey] || []).map((node) => ({
      ...node,
      work_count: liveWorkCount.get(node.id) || 0,
    }))
  }
  await fs.writeFile(path.join(STATIC_DIR, "taxonomy.json"), JSON.stringify(taxOut))

  // ---- generated pages (thin shells; client renders from the JSON) -----------
  const philCounts = {}
  for (const w of works) philCounts[w.philosopher] = (philCounts[w.philosopher] || 0) + 1
  // La scrivania: un emblema per filosofo, posato come un carteggio.
  // Il nome sta nell'HTML SOTTO la carta, non stampato nell'immagine: i modelli
  // d'immagine sbagliano le lettere (Recraft ha prodotto "RARX" e poi "MAXX"
  // per Marx), e cosi' il nome resta selezionabile, cercabile e traducibile.
  const EMBLEM = {
    Seneca: "seneca",
    Lucretius: "lucretius",
    Pascal: "pascal",
    Descartes: "descartes",
    Locke: "locke",
    Hume: "hume",
    Rousseau: "rousseau",
    Kant: "kant",
    Hegel: "hegel",
    Marx: "marx",
    Nietzsche: "nietzsche",
    "Ortega y Gasset": "ortega",
  }
  const deskCards = Object.keys(philCounts)
    .sort((a, b) => philCounts[b] - philCounts[a] || a.localeCompare(b))
    .filter((p) => EMBLEM[p])
    .map(
      (p) =>
        `  <a class="desk-card" href="opere" title="${p} - ${philCounts[p]} opere">` +
        `<img src="static/emblems/${EMBLEM[p]}.webp" alt="${p}" loading="lazy" width="400" height="400">` +
        `<span class="desk-name">${p}</span></a>`,
    )
    .join("\n")

  const home = `---
title: Filosofia — Un Grafo di Conoscenza
---

<div class="hero">
  <div class="hero-text">
    <p class="hero-kicker">Una lettura connessa della filosofia</p>
    <h1 class="hero-title">Filosofia</h1>
    <p class="hero-lead">${works.length} opere di ${Object.keys(philCounts).length} filosofi, connesse attraverso assi tematici, posizioni, concetti, argomenti, figure, forme e scuole condivisi. Apri un'opera per seguirne le connessioni; apri un concetto per vedere ogni opera che lo condivide.</p>
    <p class="hero-actions">
      <a class="btn btn-primary" href="opere">Sfoglia tutte le opere</a>
      <a class="btn" href="cerca">Cerca per tema</a>
      <a class="btn" href="assi">Esplora gli assi</a>
    </p>
  </div>
</div>

<div class="desk">
${deskCards}
</div>
`
  await fs.writeFile(path.join(CONTENT, "index.md"), home)

  const opere = `---
title: Opere
---

Tutte le **${works.length}** opere, ordinabili per colonna, paginate, con filtro testuale rapido.

<div id="opere-table"></div>
`
  await fs.writeFile(path.join(CONTENT, "opere.md"), opere)

  const cerca = `---
title: Cerca
---

Filtra le ${works.length} opere per filosofo e per ciascun asse tematico. La ricerca è language-agnostic: un passo in tedesco o in latino si trova cercando l'ID canonico o l'etichetta italiana/inglese del concetto.

<div id="cerca"></div>
`
  await fs.writeFile(path.join(CONTENT, "cerca.md"), cerca)

  const assiLines = (taxRaw.axes || [])
    .map(
      (a) =>
        `- [**${a.label_it}** / ${a.label_en}](/axes/${a.id}) — *${a.question_it}*`,
    )
    .join("\n")
  const assi = `---
title: Assi tematici
---

Le opere si connettono attraverso ${(taxRaw.axes || []).length} assi filosofici. Ogni asse apre lo spettro delle posizioni che vi si contrappongono.

${assiLines}

Puoi anche [sfogliare tutte le opere](opere) o [cercare per tema](cerca).
`
  await fs.writeFile(path.join(CONTENT, "assi.md"), assi)

  const notFound = `---
title: "Pagina non trovata"
---

<div class="nf-msg"><p><strong>Pagina non trovata.</strong></p>
<p><a href="/">Torna alla home</a></p></div>
`
  await fs.writeFile(path.join(CONTENT, "404.md"), notFound)

  console.log(
    `copied ${kgWritten} aggregator notes, ${workPages} work reading-pages; indexed ${works.length} works, ${Object.keys(philCounts).length} philosophers`,
  )
  // Un'opera senza abstract non e' un errore fatale — la pagina resta leggibile —
  // ma va detto: e' il solo modo di accorgersi che un filosofo nuovo e' stato
  // atomizzato e mai taggato.
  console.log(
    `abstract: ${abstractsEmitted}/${workPages} opere` +
      (abstractsEmitted < workPages
        ? ` — ${workPages - abstractsEmitted} senza summary_en in data/tags/`
        : ""),
  )
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
