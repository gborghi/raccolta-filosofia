// Client-side tags index: renders /static/tags.json into a searchable, sortable,
// paginated table inside #tags-table (on /tags/). Replaces the old ~48 MB server-rendered
// aggregator. Vanilla JS, no build step — copied verbatim to /static by Quartz.
// Adapted from the eng-lit opereTable component.
(function () {
  "use strict"
  var PAGE_SIZES = [25, 50, 100, 250]
  var cache = null
  // eng-lit deploys under a subpath (/raccolta-letteratura-inglese/), so absolute
  // /static and /tags links 404 — prefix everything with Quartz's basepath.
  var BP = ""

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return c === "&" ? "&amp;" : c === "<" ? "&lt;" : c === ">" ? "&gt;" : "&quot;"
    })
  }

  function buildTable(el, rows) {
    var sortKey = "count"
    var sortDir = -1 // count desc by default (most-used tags first)
    var filter = ""
    var page = 0
    var pageSize = 50

    var search = document.createElement("input")
    search.type = "search"
    search.className = "lt-search"
    search.placeholder = "Filtra " + rows.length + " tag per nome o dimensione…"

    var searchRow = document.createElement("div")
    searchRow.className = "qtable-searchrow"
    searchRow.appendChild(search)

    var meta = document.createElement("div")
    meta.className = "lt-meta"

    var table = document.createElement("table")
    table.className = "lt-table"

    var pager = document.createElement("div")
    pager.className = "lt-pager"

    // [key, label, numeric]
    var cols = [
      ["tag", "Tag", false],
      ["type", "Dimensione", false],
      ["count", "Atomi", true],
    ]
    var NUMERIC = { count: true }

    function cmp(a, b) {
      var av = a[sortKey],
        bv = b[sortKey]
      if (NUMERIC[sortKey]) {
        av = Number(av)
        bv = Number(bv)
      } else {
        av = String(av).toLowerCase()
        bv = String(bv).toLowerCase()
      }
      if (av < bv) return -sortDir
      if (av > bv) return sortDir
      return a.tag < b.tag ? -1 : 1
    }

    function filtered() {
      var q = filter.toLowerCase()
      var r = q
        ? rows.filter(function (x) {
            return x.tag.toLowerCase().indexOf(q) >= 0 || x.type.toLowerCase().indexOf(q) >= 0
          })
        : rows.slice()
      return r.sort(cmp)
    }

    function render() {
      var all = filtered()
      var pages = Math.max(1, Math.ceil(all.length / pageSize))
      if (page >= pages) page = pages - 1
      if (page < 0) page = 0
      var slice = all.slice(page * pageSize, page * pageSize + pageSize)

      var head =
        "<thead><tr>" +
        cols
          .map(function (c) {
            var k = c[0],
              label = c[1],
              num = c[2]
            var cls =
              "lt-th" +
              (num ? " lt-num" : "") +
              (sortKey === k ? " sorted-" + (sortDir > 0 ? "asc" : "desc") : "")
            return '<th data-k="' + k + '" class="' + cls + '">' + label + "</th>"
          })
          .join("") +
        "</tr></thead>"

      var body =
        "<tbody>" +
        slice
          .map(function (r) {
            return (
              '<tr><td><a class="internal" href="' + BP + '/tags/' +
              encodeURI(r.tag) +
              '">' +
              esc(r.tag) +
              "</a></td>" +
              '<td class="lt-cluster">' +
              esc(r.type) +
              "</td>" +
              '<td class="lt-num">' +
              esc(r.count) +
              "</td></tr>"
            )
          })
          .join("") +
        "</tbody>"

      table.innerHTML = head + body
      var ths = table.querySelectorAll("th.lt-th")
      for (var i = 0; i < ths.length; i++) {
        ;(function (th) {
          th.addEventListener("click", function () {
            var k = th.getAttribute("data-k")
            if (sortKey === k) sortDir *= -1
            else {
              sortKey = k
              sortDir = NUMERIC[k] ? -1 : 1
            }
            render()
          })
        })(ths[i])
      }

      meta.innerHTML = "<span><strong>" + all.length + "</strong> tag</span>"
      var sel = document.createElement("select")
      PAGE_SIZES.forEach(function (s) {
        var o = document.createElement("option")
        o.value = String(s)
        o.textContent = s + " / pagina"
        if (s === pageSize) o.selected = true
        sel.appendChild(o)
      })
      sel.addEventListener("change", function () {
        pageSize = Number(sel.value)
        page = 0
        render()
      })
      meta.appendChild(sel)

      pager.innerHTML = ""
      function btn(label, disabled, fn) {
        var b = document.createElement("button")
        b.textContent = label
        b.disabled = disabled
        b.addEventListener("click", fn)
        return b
      }
      pager.appendChild(
        btn("« Prima", page === 0, function () {
          page = 0
          render()
        }),
      )
      pager.appendChild(
        btn("‹ Prec", page === 0, function () {
          page--
          render()
        }),
      )
      var info = document.createElement("span")
      info.className = "lt-page-info"
      info.textContent = "Pagina " + (page + 1) + " di " + pages
      pager.appendChild(info)
      pager.appendChild(
        btn("Succ ›", page >= pages - 1, function () {
          page++
          render()
        }),
      )
      pager.appendChild(
        btn("Ultima »", page >= pages - 1, function () {
          page = pages - 1
          render()
        }),
      )
    }

    search.addEventListener("input", function () {
      filter = search.value
      page = 0
      render()
    })

    el.replaceChildren(searchRow, meta, table, pager)
    render()
  }

  function init() {
    var root = document.getElementById("tags-table")
    if (!root || root.dataset.rendered) return
    root.dataset.rendered = "1"
    BP = (document.body && document.body.dataset.basepath) || ""
    var go = function (data) {
      buildTable(root, data)
    }
    if (cache) return go(cache)
    fetch(BP + "/static/tags.json")
      .then(function (r) {
        return r.json()
      })
      .then(function (j) {
        cache = j
        go(j)
      })
      .catch(function () {
        root.textContent = "Impossibile caricare l'indice dei tag."
      })
  }

  document.addEventListener("nav", init)
  if (document.readyState !== "loading") init()
  else document.addEventListener("DOMContentLoaded", init)
})()
