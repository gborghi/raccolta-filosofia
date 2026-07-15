// Reusable radial "option wheel": renders <div class="radial-wheel" data-wheel="...">
// placeholders into a circle of clickable emblem tiles, with a center medallion and
// upright labels placed on the INNER side of each emblem in a top layer (so a label
// is always in the foreground and never hidden when the emblem is hovered/scaled).
// A grid fallback kicks in on narrow screens. Data: quartz/static/wheel.json.

interface Spoke {
  label: string
  sub?: string
  img: string
  href: string
  cercaAuthor?: string
}
type WheelData = Record<string, Spoke[]>

let cache: WheelData | null = null
async function load(prefix: string): Promise<WheelData> {
  if (cache) return cache
  cache = (await (await fetch(prefix + "static/wheel.json")).json()) as WheelData
  return cache
}

function esc(s: unknown): string {
  return String(s).replace(/[&<>"]/g, (c) =>
    c === "&" ? "&amp;" : c === "<" ? "&lt;" : c === ">" ? "&gt;" : "&quot;",
  )
}

// point an author emblem straight at that author's landing page (content/authors/<slug>).
// (wheel.json still ships href:"cerca" + cercaAuthor for back-compat; we rewrite here.)
function wireCerca(a: HTMLAnchorElement, s: Spoke) {
  if (!s.cercaAuthor) return
  a.dataset.author = s.cercaAuthor
  const cur = a.getAttribute("href") || ""
  // Slugify the author name for the landing-page URL: multi-word authors (e.g.
  // "Conan Doyle") emit at /authors/conan-doyle, so spaces must become hyphens —
  // otherwise the link is /authors/conan%20doyle which 404s.
  const slug = s.cercaAuthor.toLowerCase().replace(/\s+/g, "-")
  a.setAttribute("href", cur.replace(/cerca\/?$/, "authors/" + slug))
}

// emblem-only clickable tile (circle layout)
function buildTile(s: Spoke, prefix: string, imgPrefix: string): HTMLAnchorElement {
  const a = document.createElement("a")
  a.className = "rw-spoke rw-tilespoke"
  a.href = prefix + s.href
  a.setAttribute("aria-label", s.label)
  wireCerca(a, s)
  a.innerHTML = `<span class="rw-tile"><img src="${imgPrefix}static/wheel/${esc(
    s.img,
  )}.webp" alt="${esc(s.label)} emblem" loading="lazy" width="320" height="320"></span>`
  return a
}

// standalone label chip (circle layout, lives in the top label layer)
function buildLabelAnchor(s: Spoke, prefix: string): HTMLAnchorElement {
  const a = document.createElement("a")
  a.className = "rw-label-anchor"
  a.href = prefix + s.href
  wireCerca(a, s)
  a.innerHTML =
    `<span class="rw-label">${esc(s.label)}</span>` +
    (s.sub ? `<span class="rw-sub">${esc(s.sub)}</span>` : "")
  return a
}

// combined tile+label stack, used only by the narrow-screen grid fallback
function buildCombined(s: Spoke, prefix: string, imgPrefix: string): HTMLAnchorElement {
  const a = document.createElement("a")
  a.className = "rw-spoke"
  a.href = prefix + s.href
  wireCerca(a, s)
  a.innerHTML =
    `<span class="rw-tile"><img src="${imgPrefix}static/wheel/${esc(
      s.img,
    )}.webp" alt="${esc(s.label)} emblem" loading="lazy" width="320" height="320"></span>` +
    `<span class="rw-label">${esc(s.label)}` +
    (s.sub ? `<span class="rw-sub">${esc(s.sub)}</span>` : "") +
    `</span>`
  return a
}

// The circular shingle has ONE unavoidable seam: z-index is a total order, but
// "every tile above one neighbour, below the other" is a *cyclic* relation, so no
// single z per tile can satisfy it — one tile ends up below both its neighbours.
// Heal it in GEOMETRY, not paint-order: draw a clipped duplicate of the seam tile,
// clipped to just the sliver where it overlaps its counter-clockwise (higher-z)
// neighbour, and float that sliver on top. The seam tile then reads below its
// clockwise neighbour (original) yet above its counter-clockwise one (the sliver),
// closing the cycle with no visible break. Returns the seam index used by layout.
//
// clip to the half-plane through the tile-box centre whose kept side faces (dx,dy);
// Sutherland–Hodgman clip of the 0..100% square by that one plane.
function halfPlaneClip(dx: number, dy: number): string {
  const sq: [number, number][] = [
    [0, 0],
    [100, 0],
    [100, 100],
    [0, 100],
  ]
  const f = (p: [number, number]) => (p[0] - 50) * dx + (p[1] - 50) * dy
  const out: [number, number][] = []
  for (let i = 0; i < 4; i++) {
    const a = sq[i]
    const b = sq[(i + 1) % 4]
    const fa = f(a)
    const fb = f(b)
    if (fa >= 0) out.push(a)
    if (fa < 0 !== fb < 0) {
      const t = fa / (fa - fb)
      out.push([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])])
    }
  }
  return "polygon(" + out.map((p) => `${p[0].toFixed(1)}% ${p[1].toFixed(1)}%`).join(",") + ")"
}

function healSeam(stage: HTMLElement, tiles: HTMLElement[], before: Node, n: number) {
  if (n < 3) return
  const seam = Math.round(n / 2) // the tile left below both neighbours (base --rw-z 0)
  const ccw = (seam - 1 + n) % n // its counter-clockwise neighbour (highest --rw-z)
  const S = tiles[seam]
  const P = tiles[ccw]
  const sx = parseFloat(S.style.left)
  const sy = parseFloat(S.style.top)
  const dx = parseFloat(P.style.left) - sx // point the kept half at the ccw neighbour
  const dy = parseFloat(P.style.top) - sy
  const dup = S.cloneNode(true) as HTMLElement
  dup.classList.add("rw-seamfix")
  dup.removeAttribute("href")
  dup.setAttribute("aria-hidden", "true")
  dup.style.pointerEvents = "none"
  dup.style.setProperty("--rw-z", String(n)) // above every base tile, below hover(25)/labels(30)
  dup.style.clipPath = halfPlaneClip(dx, dy)
  stage.insertBefore(dup, before) // above tiles, beneath centre medallion + labels
}

function layoutCircle(tiles: HTMLElement[], labels: HTMLElement[]) {
  const n = tiles.length
  const tileR = 37 // emblem ring radius (% of stage)
  // For crowded wheels (≥10 spokes) alternate between two inner radii so adjacent
  // labels sit at different distances and don't overlap each other.
  const crowded = n >= 10
  const labelR_inner = crowded ? 20 : 22 // closer ring (even spokes)
  // Wide inner/outer spread on crowded wheels so adjacent labels sit at very different
  // radii — long multi-word cluster names ("Unrequited Frustrated Love") otherwise
  // collide with their neighbours. 33 is still inside the emblem ring (tileR 37).
  const labelR_outer = crowded ? 33 : 22 // farther ring (odd spokes, still inner side)
  // A circular shingle can only ever be monotone up to ONE seam — z-index is a
  // total order, so somewhere around the ring the "each tile above its counter-
  // clockwise neighbour" rule must reverse. Only immediate neighbours overlap
  // (tile Ø 27% vs. ~30% next-nearest spacing), so that reversal is a single
  // adjacent pair; park it at the BOTTOM (6 o'clock), the least-noticed spot,
  // instead of the upper-left tile the old (i+1)%n formula left it on (which put
  // Wilde/Sea under both their neighbours). `seam` = the lowest tile, chosen so
  // the reversed pair straddles the bottom; z then climbs clockwise from it, so
  // every visible upper-arc overlap (e.g. Whitman<Wilde<Austen<Belloc) is
  // consistent.
  const seam = Math.round(n / 2)
  for (let i = 0; i < n; i++) {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2 // start at 12 o'clock
    const cos = Math.cos(angle)
    const sin = Math.sin(angle)
    const t = tiles[i]
    t.style.left = 50 + tileR * cos + "%"
    t.style.top = 50 + tileR * sin + "%"
    // Write the base stacking order as a CSS variable (NOT an inline z-index):
    // an inline z-index would outrank the stylesheet `.rw-tilespoke:hover`
    // rule, so hovering could no longer raise a tile above its neighbours.
    t.style.setProperty("--rw-z", String((i - seam + n) % n))
    const labelR = i % 2 === 0 ? labelR_inner : labelR_outer
    const l = labels[i]
    l.style.left = 50 + labelR * cos + "%"
    l.style.top = 50 + labelR * sin + "%"
  }
}

function renderWheel(root: HTMLElement, spokes: Spoke[], prefix: string, imgPrefix: string) {
  const title = root.dataset.center || ""
  const sub = root.dataset.centerSub || ""

  const stage = document.createElement("div")
  stage.className = "rw-stage"
  const ring = document.createElement("div")
  ring.className = "rw-ring"
  stage.appendChild(ring)

  const center = document.createElement("div")
  center.className = "rw-center"
  center.innerHTML =
    `<span class="rw-center-title">${esc(title)}</span>` +
    (sub ? `<span class="rw-center-sub">${esc(sub)}</span>` : "")

  const tiles: HTMLElement[] = []
  const labels: HTMLElement[] = []
  const fallback = document.createElement("div")
  fallback.className = "rw-fallback"

  for (const s of spokes) {
    tiles.push(buildTile(s, prefix, imgPrefix))
    labels.push(buildLabelAnchor(s, prefix))
    fallback.appendChild(buildCombined(s, prefix, imgPrefix))
  }
  // Mark crowded wheels so CSS can reduce label font size
  if (spokes.length >= 10) stage.dataset.crowded = "1"
  // paint order: ring -> tiles -> center medallion -> LABELS (top layer)
  for (const t of tiles) stage.appendChild(t)
  stage.appendChild(center)
  for (const l of labels) stage.appendChild(l)
  layoutCircle(tiles, labels)
  // geometry-based seam heal: clipped duplicate goes above the tiles but beneath the
  // centre medallion (the first node appended after the tiles).
  healSeam(stage, tiles, center, tiles.length)

  root.replaceChildren(stage, fallback)

  const apply = () => {
    const narrow = root.clientWidth < 460
    root.classList.toggle("rw-grid", narrow)
  }
  apply()
  if ("ResizeObserver" in window) {
    const ro = new ResizeObserver(apply)
    ro.observe(root)
  } else {
    window.addEventListener("resize", apply)
  }
}

async function init() {
  const roots = Array.from(
    document.querySelectorAll<HTMLElement>("div.radial-wheel"),
  ).filter((el) => !el.dataset.rendered)
  if (!roots.length) return

  const slug = document.body.dataset.slug || ""
  const prefix = "../".repeat((slug.match(/\//g) || []).length)
  let data: WheelData
  try {
    data = await load(prefix)
  } catch {
    return
  }

  for (const root of roots) {
    root.dataset.rendered = "1"
    const key = root.dataset.wheel || ""
    const spokes = data[key]
    if (!spokes) continue
    renderWheel(root, spokes, prefix, prefix)
  }
}

document.addEventListener("nav", () => {
  init()
})
init()

export {}
