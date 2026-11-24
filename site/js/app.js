(function () {
  "use strict";

  var DATA_URL = "data/signal.json";
  var instrument = null;

  function $(id) { return document.getElementById(id); }

  function fmtP(x) {
    if (x == null || Number.isNaN(x)) return "—";
    return Number(x).toFixed(3);
  }

  function fmtInterval(lo, hi) {
    if (lo == null || hi == null) return "—";
    return "[" + Number(lo).toFixed(3) + ", " + Number(hi).toFixed(3) + "]";
  }

  function fmtMoney(x) {
    if (x == null || Number.isNaN(x)) return "—";
    var n = Number(x);
    var abs = Math.abs(n);
    var sign = n < 0 ? "−" : "";
    if (abs >= 1e9) return sign + "$" + (abs / 1e9).toFixed(2) + "b";
    if (abs >= 1e6) return sign + "$" + (abs / 1e6).toFixed(2) + "m";
    if (abs >= 1e3) return sign + "$" + (abs / 1e3).toFixed(1) + "k";
    return sign + "$" + abs.toFixed(0);
  }

  function fmtPx(x) {
    if (x == null || Number.isNaN(x)) return "—";
    var n = Number(x);
    if (n >= 1000) return n.toLocaleString("en-US", { maximumFractionDigits: 1 });
    if (n >= 1) return n.toFixed(2);
    return n.toPrecision(4);
  }

  function fmtSize(x) {
    if (x == null || Number.isNaN(x)) return "—";
    return Math.abs(Number(x)).toLocaleString("en-US", { maximumFractionDigits: 4 });
  }

  function shortAddr(a) {
    if (!a) return "—";
    if (a.length < 12) return a;
    return a.slice(0, 6) + "…" + a.slice(-4);
  }

  function ageLabel(tsUtc) {
    if (!tsUtc) return "unknown";
    var t = Date.parse(tsUtc);
    if (Number.isNaN(t)) return "unknown";
    var sec = Math.max(0, (Date.now() - t) / 1000);
    if (sec < 60) return "under 1 min";
    if (sec < 3600) return Math.round(sec / 60) + " min";
    if (sec < 86400) return (sec / 3600).toFixed(1) + " h";
    return (sec / 86400).toFixed(1) + " d";
  }

  function showStatus(text, isError) {
    var el = $("status");
    el.hidden = !text;
    el.textContent = text || "";
    el.classList.toggle("is-error", !!isError);
  }

  function renderSparkline(history) {
    var svg = $("history-chart");
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var ns = "http://www.w3.org/2000/svg";
    var w = 1000, h = 72, pad = 8;
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    svg.setAttribute("preserveAspectRatio", "none");
    function line(x1, y1, x2, y2, stroke, width, dash) {
      var el = document.createElementNS(ns, "line");
      el.setAttribute("x1", x1); el.setAttribute("y1", y1);
      el.setAttribute("x2", x2); el.setAttribute("y2", y2);
      el.setAttribute("stroke", stroke);
      el.setAttribute("stroke-width", width);
      el.setAttribute("vector-effect", "non-scaling-stroke");
      if (dash) el.setAttribute("stroke-dasharray", dash);
      svg.appendChild(el);
    }
    var innerH = h - pad * 2;
    function yOf(p) { return pad + innerH * (1 - p); }
    line(0, yOf(0.5), w, yOf(0.5), "#141414", 1);
    line(0, yOf(0.6), w, yOf(0.6), "#B7B3A9", 1, "2 3");
    line(0, yOf(0.4), w, yOf(0.4), "#B7B3A9", 1, "2 3");
    var pts = (history || []).filter(function (d) { return d.p_long != null; });
    var note = document.getElementById("history-note");
    if (note) {
      if (pts.length < 2) {
        note.hidden = false;
        note.textContent = pts.length === 1
          ? "One snapshot stored; the strip will fill as later sweeps arrive."
          : "No stored history yet.";
      } else {
        note.hidden = true;
        note.textContent = "";
      }
    }
    if (pts.length < 2) {
      return;
    }
    var d = "";
    pts.forEach(function (pt, i) {
      var x = (i / (pts.length - 1)) * w;
      var y = yOf(Number(pt.p_long));
      d += (i === 0 ? "M" : "L") + x.toFixed(2) + " " + y.toFixed(2);
    });
    var path = document.createElementNS(ns, "path");
    path.setAttribute("d", d);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "#8C1D12");
    path.setAttribute("stroke-width", "1.5");
    path.setAttribute("vector-effect", "non-scaling-stroke");
    svg.appendChild(path);
  }

  function fillTable(id, headers, rows) {
    var table = $(id);
    table.innerHTML = "";
    var thead = document.createElement("thead");
    var tr = document.createElement("tr");
    headers.forEach(function (h) {
      var th = document.createElement("th");
      th.scope = "col";
      th.textContent = h;
      tr.appendChild(th);
    });
    thead.appendChild(tr);
    table.appendChild(thead);
    var tbody = document.createElement("tbody");
    rows.forEach(function (cols) {
      var r = document.createElement("tr");
      cols.forEach(function (c, i) {
        var td = document.createElement("td");
        td.textContent = c;
        r.appendChild(td);
      });
      tbody.appendChild(r);
    });
    table.appendChild(tbody);
  }

  function apply(data) {
    var verdict = data.verdict || "NEUTRAL";
    $("verdict").textContent = verdict;
    $("verdict").classList.toggle("is-neutral", verdict === "NEUTRAL");
    $("p-long").textContent = fmtP(data.p_long);
    $("interval").textContent = fmtInterval(data.ci_low, data.ci_high);
    $("sample").textContent =
      String(data.n_traders != null ? data.n_traders : "—") +
      "  (L " + (data.n_long || 0) +
      " / S " + (data.n_short || 0) +
      " / flat " + (data.n_flat || 0) + ")";
    $("issued").textContent = data.ts_ist || "—";
    $("freshness").textContent = "Data age  " + ageLabel(data.ts_utc);
    $("btc-mark").textContent = data.btc_mark != null ? fmtPx(data.btc_mark) : "—";
    var notes = (data.notes || []).join(" ");
    $("reading-note").textContent = notes;

    var ageMs = data.ts_utc ? Date.now() - Date.parse(data.ts_utc) : 0;
    if (ageMs > 2 * 3600 * 1000) {
      showStatus("This snapshot is older than two hours. A later sweep may not have run.", true);
    } else {
      showStatus("");
    }

    if (instrument) instrument.setReading(data.p_long);

    fillTable("counts-table", ["", "Long", "Short", "Flat"], [
      ["Wallets", data.n_long || 0, data.n_short || 0, data.n_flat || 0],
      ["BTC notional", fmtMoney(data.notional_long), fmtMoney(data.notional_short), "—"]
    ]);

    var longN = Number(data.notional_long) || 0;
    var shortN = Number(data.notional_short) || 0;
    var tot = longN + shortN;
    $("stack-long").style.width = tot ? (100 * longN / tot).toFixed(2) + "%" : "0%";
    $("stack-short").style.width = tot ? (100 * shortN / tot).toFixed(2) + "%" : "0%";
    $("stack-caption").textContent = tot
      ? "Ink is long notional; the open remainder is short notional."
      : "No BTC notional in the cohort.";

    var buckets = data.size_buckets || [];
    fillTable(
      "buckets-table",
      ["Notional band", "Long", "Short", "Long $", "Short $"],
      buckets.map(function (b) {
        return [
          b.label,
          b.long_count,
          b.short_count,
          fmtMoney(b.notional_long),
          fmtMoney(b.notional_short)
        ];
      })
    );

    var positions = data.top_positions || [];
    fillTable(
      "positions-table",
      ["Address", "Side", "Size (BTC)", "Entry", "Leverage", "uPnL"],
      positions.map(function (p) {
        var lev = p.leverage != null
          ? String(p.leverage) + "×" + (p.leverage_type ? " " + p.leverage_type : "")
          : "—";
        return [
          shortAddr(p.address),
          p.side,
          fmtSize(p.size),
          fmtPx(p.entry),
          lev,
          fmtMoney(p.unrealized_pnl)
        ];
      })
    );

    renderSparkline(data.history || []);
    document.title = verdict + " — BTC consensus, Hyperliquid one-month leaders";
  }

  function fallbackDial() {
    $("inclination").hidden = true;
    $("sphere-fallback").hidden = false;
  }

  function boot() {
    var canvas = $("inclination");
    if (canvas && canvas.getContext && typeof window.createInclination === "function") {
      try {
        instrument = window.createInclination(canvas);
      } catch (err) {
        fallbackDial();
      }
    } else {
      fallbackDial();
    }

    fetch(DATA_URL, { cache: "no-store" })
      .then(function (res) {
        if (!res.ok) throw new Error("signal.json HTTP " + res.status);
        return res.json();
      })
      .then(apply)
      .catch(function (err) {
        showStatus("No snapshot yet. Run the sweep, then reload this page. (" + err.message + ")", true);
        renderSparkline([]);
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
