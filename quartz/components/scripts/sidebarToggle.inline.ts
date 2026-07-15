// Global left-sidebar open/close — one reliable toggle for the whole site.
//
// Quartz's own Explorer toggles (desktop fold + mobile hamburger) are inert in this
// build, and the reading-page drawer used to overlay/dim the page (hiding the reader's
// own chapter TOC). This owns the behaviour, in three breakpoint-dependent modes because
// each surface has a different sensible target and default:
//
//   • desktop, normal page (>=800px, no reader): the left sidebar is a static column,
//     SHOWN by default. The fixed ☰/✕ collapses the whole column (body.left-collapsed)
//     to widen the reading area, and reopens it.
//   • desktop, reading page (>=800px, body.reading-page): the sidebar is HIDDEN by
//     default. The toggle reveals it (body.left-open) which — per custom.scss — squeezes
//     the page right (the reader's chapter TOC stays visible), it does not overlay.
//   • mobile (<800px, any page): the sidebar is the top bar (title/search/icons) which
//     must stay reachable, so only the Explorer nav collapses. The existing core
//     hamburger (whose own handler is dead) gets a working handler toggling
//     body.explorer-open, shown as an overlay drawer with a scrim.
//
// Close affordances for the mobile overlay: the hamburger again, Escape, click-outside.

const OVERLAY_MAX = 800 // px; below this the sidebar top bar stays and only .explorer toggles

const body = () => document.body
const has = (c: string) => body().classList.contains(c)

function overlayMode(): boolean {
  return window.matchMedia(`(max-width: ${OVERLAY_MAX - 0.02}px)`).matches
}
function readingPage(): boolean {
  return has("reading-page")
}

type Mode = "mobile" | "reading" | "desktop"
function mode(): Mode {
  if (overlayMode()) return "mobile"
  return readingPage() ? "reading" : "desktop"
}

function isOpen(): boolean {
  switch (mode()) {
    case "mobile":
      return has("explorer-open")
    case "reading":
      return has("left-open")
    default:
      return !has("left-collapsed") // desktop: shown unless explicitly collapsed
  }
}

function setOpen(open: boolean): void {
  const cl = body().classList
  switch (mode()) {
    case "mobile":
      cl.toggle("explorer-open", open)
      break
    case "reading":
      cl.toggle("left-open", open)
      break
    default:
      cl.toggle("left-collapsed", !open)
  }
  // glyph/aria follow via the MutationObserver below.
}

let toggleBtn: HTMLButtonElement | null = null

function syncChrome(): void {
  const open = isOpen()
  // body.nav-open lets the fixed toggle move to the sidebar's top-right corner while
  // open (clear of the title) and back to the screen corner while closed — see
  // custom.scss. toggle(force) is idempotent, so this does not retrigger the observer.
  document.body.classList.toggle("nav-open", open)
  if (toggleBtn) {
    toggleBtn.innerHTML = open ? "&#10005;" : "&#9776;" // ✕ / ☰
    toggleBtn.setAttribute("aria-expanded", String(open))
    toggleBtn.title = open ? "Chiudi il menu laterale" : "Apri il menu laterale"
  }
  document
    .querySelectorAll<HTMLButtonElement>(".explorer-toggle")
    .forEach((b) => b.setAttribute("aria-expanded", String(open)))
}

let wired = false
function wireOnce(): void {
  if (wired) return
  wired = true

  // Fixed desktop toggle (hidden < OVERLAY_MAX via CSS). Collapses/expands the column.
  toggleBtn = document.createElement("button")
  toggleBtn.type = "button"
  toggleBtn.className = "site-nav-toggle"
  toggleBtn.setAttribute("aria-label", "Apri o chiudi il menu laterale")
  toggleBtn.addEventListener("click", (e) => {
    e.stopPropagation()
    setOpen(!isOpen())
  })
  body().appendChild(toggleBtn)

  // Reuse the core hamburgers (their own handlers are dead). Delegated so it also
  // covers buttons re-rendered on SPA navigation.
  document.addEventListener("click", (e) => {
    const t = e.target as HTMLElement
    if (t.closest?.(".explorer-toggle")) {
      e.stopPropagation()
      setOpen(!isOpen())
    }
  })

  // Escape closes the mobile overlay.
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && mode() === "mobile" && isOpen()) setOpen(false)
  })

  // Click outside the open mobile overlay closes it.
  document.addEventListener("click", (e) => {
    if (mode() !== "mobile" || !isOpen()) return
    const t = e.target as HTMLElement
    if (t.closest?.(".explorer") || t.closest?.(".sidebar.left") || t.closest?.(".site-nav-toggle"))
      return
    setOpen(false)
  })

  // Keep the toggle glyph honest no matter who flips the state classes.
  new MutationObserver(syncChrome).observe(body(), {
    attributes: true,
    attributeFilter: ["class"],
  })
}

function init(): void {
  wireOnce()
  // Each navigation may change page type (atomRouter sets body.reading-page). Reset the
  // transient open-states to each mode's default so the toggle starts predictable.
  body().classList.remove("explorer-open")
  if (!readingPage()) body().classList.remove("left-collapsed")
  syncChrome()
}

document.addEventListener("nav", init)
init()
