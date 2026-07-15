// Loading spinner for the built-in (top-bar) search.
//
// The upstream search plugin (github:quartz-community/search, restored into
// .quartz/ and therefore not durably patchable here) fetches a large
// contentIndex (~21MB mobile / ~34MB desktop) and builds a FlexSearch index on
// the main thread inside its "nav" handler — and does so BEFORE wiring the
// button's click handler. So for the first tens of seconds after page load the
// search is not merely slow, it is inert, with zero feedback. This committed
// script shows a spinner on the search button until the index has loaded, so a
// visitor knows to wait instead of assuming the search is broken.
//
// Readiness is inferred without touching the plugin: watch for the contentIndex
// network request to finish (PerformanceObserver), then wait for the main thread
// to settle (the synchronous FlexSearch build) before hiding.

const IDX_RE = /contentIndex(Mobile)?\.json(\?|$)/

let indexReady = false
let watching = false

function getSearch(): { search: Element; btn: HTMLElement } | null {
  const search = document.querySelector(".search")
  if (!search) return null
  const btn = search.querySelector(".search-button") as HTMLElement | null
  if (!btn) return null
  return { search, btn }
}

function showSpinner() {
  const f = getSearch()
  if (!f) return
  f.search.classList.add("search-loading")
  f.btn.setAttribute("aria-busy", "true")
  f.btn.setAttribute("title", "Caricamento indice di ricerca…")
  if (!f.btn.querySelector(".search-index-spinner")) {
    const s = document.createElement("span")
    s.className = "search-index-spinner"
    s.setAttribute("aria-hidden", "true")
    f.btn.appendChild(s)
  }
}

function hideSpinner() {
  indexReady = true
  const search = document.querySelector(".search")
  if (!search) return
  search.classList.remove("search-loading")
  const btn = search.querySelector(".search-button") as HTMLElement | null
  if (!btn) return
  btn.removeAttribute("aria-busy")
  btn.removeAttribute("title")
  const s = btn.querySelector(".search-index-spinner")
  if (s) s.remove()
}

// After the index finishes downloading the plugin still spends real time filling
// FlexSearch synchronously. Wait for a healthy idle slice (main thread free)
// before hiding so the spinner doesn't disappear mid-build.
function hideWhenIdle(started: number) {
  const ric = (window as unknown as {
    requestIdleCallback?: (cb: (d: { timeRemaining: () => number }) => void, o?: { timeout: number }) => number
  }).requestIdleCallback
  const attempt = () => {
    if (indexReady) return
    if (ric) {
      ric(
        (deadline) => {
          if (deadline.timeRemaining() > 20 && performance.now() - started > 150) {
            hideSpinner()
          } else {
            setTimeout(attempt, 120)
          }
        },
        { timeout: 500 },
      )
    } else {
      setTimeout(hideSpinner, 400)
    }
  }
  attempt()
}

function indexAlreadyDownloaded(): boolean {
  return performance
    .getEntriesByType("resource")
    .some((e) => IDX_RE.test(e.name) && (e as PerformanceResourceTiming).responseEnd > 0)
}

function watchOnce() {
  if (watching || indexReady) return
  watching = true
  const start = performance.now()

  if (indexAlreadyDownloaded()) {
    hideWhenIdle(start)
    return
  }

  try {
    const obs = new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        if (IDX_RE.test(e.name)) {
          obs.disconnect()
          hideWhenIdle(performance.now())
          return
        }
      }
    })
    obs.observe({ type: "resource", buffered: true })
  } catch {
    const poll = () => {
      if (indexAlreadyDownloaded()) hideWhenIdle(performance.now())
      else if (performance.now() - start < 90000) setTimeout(poll, 300)
      else hideSpinner()
    }
    poll()
  }

  // absolute safety net: never leave the spinner stuck
  setTimeout(() => {
    if (!indexReady) hideSpinner()
  }, 90000)
}

function onNav() {
  if (indexReady) return // already loaded (SPA re-navigation) — module scope persists
  showSpinner()
  watchOnce()
}

document.addEventListener("nav", onNav)
onNav()

export {}
