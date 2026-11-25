/* Flows tab: flow box, top vs worst-performing cohort, whale tape, liquidations.
   Reads data.intel.tracker from signal.json. */
(function () {
  "use strict";
  var H = window.HLCharts;
  var C = H.C;
  var S = { data: null, win: null, filter: "all" };

  function $(id) { return document.getElementById(id); }
  function num(x) { return x != null && !isNaN(x); }
  function money(x, signed) {
    if (!num(x)) return "—";
    var a = Math.abs(x), s = x < 0 ? "−" : (signed && x > 0 ? "+" : "");
    if (a >= 1e9) return s + "$" + (a / 1e9).toFixed(2) + "b";
    if (a >= 1e6) return s + "$" + (a / 1e6).toFixed(2) + "m";
    if (a >= 1e3) return s + "$" + (a / 1e3).toFixed(0) + "k";
    return s + "$" + a.toFixed(0);
  }
  function cell(x) {
    if (!num(x)) return "—";
    var a = Math.abs(x), s = x < 0 ? "−" : "";
    if (a < 500) return "0";
    if (a >= 1e9) return s + (a / 1e9).toFixed(2) + "b";
    if (a >= 1e6) return s + (a / 1e6).toFixed(2) + "m";
    return s + (a / 1e3).toFixed(0) + "k";
  }
  function signedCell(x) { return num(x) && x > 500 ? "+" + cell(x) : cell(x); }
  function pct(x, d) { return num(x) ? (x * 100).toFixed(d == null ? 1 : d) + "%" : "—"; }
  function spct(x, d) { return num(x) ? (x > 0 ? "+" : (x < 0 ? "−" : "")) + Math.abs(x * 100).toFixed(d == null ? 1 : d) + "%" : "—"; }
  function px(x) { return num(x) ? Number(x).toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—"; }
  function addr(a) { return a && a.length > 12 ? a.slice(0, 6) + "…" + a.slice(-4) : (a || "—"); }
  function ago(ms) {
    if (!ms) return "—";
    var m = Math.max(0, Math.round((Date.now() - ms) / 60000));
    if (m < 60) return m + " min ago";
    var h = Math.floor(m / 60);
    if (h < 48) return h + " h " + (m % 60) + " min ago";
    return Math.floor(h / 24) + " d ago";
  }
  var CLOCK = typeof Intl !== "undefined" ? new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false }) : null;
  function clock(ms) { return ms ? (CLOCK ? CLOCK.format(new Date(ms)) : new Date(ms).toISOString().slice(11, 16)) + " IST" : "—"; }
  function stamp(ms) { return ms ? H.fmtTime(ms) + " IST" : "—"; }
  function txt(id, s) { var e = $(id); if (e) e.textContent = s == null ? "" : s; }
  function mk(tag, cls, text, parent) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function cohortName(c) { return c === "smart" ? "Top cohort" : (c === "contrast" ? "Worst-performing cohort" : "Untracked wallet"); }
  function link(a) {
    var x = document.createElement("a");
    x.href = "https://app.hyperliquid.xyz/explorer/address/" + a;
    x.textContent = addr(a);
    x.rel = "noopener";
    x.target = "_blank";
    x.title = a;
    return x;
  }

  function T() { return (S.data && S.data.intel && S.data.intel.tracker) || null; }
  function W() {
    var t = T();
    return t && t.flow && t.flow.windows ? t.flow.windows[S.win] : null;
  }

  // ------------------------------------------------------------- timeframe
  function timeframes(t) {
    var box = $("fl-tf");
    box.innerHTML = "";
    var order = (t.flow && t.flow.order) || [];
    if (!S.win || !(t.flow.windows[S.win] || {}).available) S.win = t.flow.default || "4h";
    order.forEach(function (lab) {
      var w = t.flow.windows[lab] || {};
      var b = mk("button", null, lab, box);
      b.type = "button";
      b.setAttribute("aria-pressed", lab === S.win ? "true" : "false");
      if (!w.available) {
        b.disabled = true;
        b.title = "Building history: " + (((w.smart || {}).reason) || "not enough stored snapshots yet.");
        b.setAttribute("aria-label", lab + ", building history");
      }
      b.addEventListener("click", function () { S.win = lab; render(); });
    });
  }

  // ------------------------------------------------------------- reading 1-3
  function reading(t) {
    var e = t.explain || {};
    var sm = (t.cohorts || {}).smart || {};
    if (num(e.short_share)) {
      var short = e.short_share >= 0.5;
      var share = short ? e.short_share : 1 - e.short_share;
      txt("fl-main", pct(share, 1) + " " + (short ? "short" : "long"));
      var per = Math.round(share * 100);
      var chg = "";
      if (num(e.short_share_12h_ago)) {
        var d = (e.short_share - e.short_share_12h_ago) * 100;
        chg = " Twelve hours ago it was " + pct(e.short_share_12h_ago, 1) + " short (" + (d >= 0 ? "+" : "−") + Math.abs(d).toFixed(1) + " points).";
      } else {
        chg = " The 12-hour change appears once 12 hours of snapshots are stored.";
      }
      txt("fl-main-t", "Of every $100 the top cohort has in open BTC positions, $" + per + " is " + (short ? "short" : "long") + "." + chg);
    } else {
      txt("fl-main", "—");
      txt("fl-main-t", "The top cohort holds no open BTC positions in this snapshot.");
    }
    txt("fl-sides", money(e.long_ntl) + " long · " + money(e.short_ntl) + " short");
    txt("fl-sides-t", (e.n_long || 0) + " wallets net long, " + (e.n_short || 0) + " net short, of " + (sm.members || 0) +
      ". Compare dollars with wallets: a few large wallets can outweigh many small ones.");
    var w = W();
    var ws = w && w.smart;
    txt("fl-last-k", "The last " + (w ? phrase(w.hours) : "4 hours"));
    if (ws && ws.available) {
      txt("fl-last", "longs " + money(ws.longs_net, true) + " · shorts " + money(ws.shorts_net, true));
      var sn = ws.shorts_net, ln = ws.longs_net;
      txt("fl-last-t", "Shorts " + money(sn, true) + " means the top cohort is " + money(Math.abs(sn)) + " " + (sn >= 0 ? "more" : "less") +
        " short than at " + clock(ws.base_ms) + "; longs " + money(ln, true) + " means it is " + money(Math.abs(ln)) + " " + (ln >= 0 ? "more" : "less") + " long.");
    } else {
      txt("fl-last", "building history");
      txt("fl-last-t", ws ? ws.reason : "No window selected.");
    }
  }
  function phrase(h) { return { 1: "hour", 4: "4 hours", 8: "8 hours", 12: "12 hours", 24: "24 hours", 48: "48 hours", 168: "week" }[h] || h + " hours"; }

  // ------------------------------------------------------------- flow box
  function flowBox(t) {
    var w = W();
    txt("fl-win-name", "past " + (S.win || "4h"));
    var ws = w && w.smart;
    var tb = $("fl-flow-table");
    if (!ws || !ws.available) {
      txt("fl-flow-kicker", "Building history");
      txt("fl-longs", "—");
      txt("fl-shorts", "—");
      txt("fl-flow-sentence", ws ? ws.reason : "Waiting for the first two snapshots.");
      tb.innerHTML = "<tbody><tr><td>" + (ws ? ws.reason : "Building history.") + "</td></tr></tbody>";
      return;
    }
    var ln = ws.longs_net, sn = ws.shorts_net;
    var k;
    if (Math.abs(ln) < 1 && Math.abs(sn) < 1) k = "No change";
    else if (Math.abs(ln) >= Math.abs(sn)) k = ln > 0 ? "Adding to longs" : "Cutting longs";
    else k = sn > 0 ? "Adding to shorts" : "Cutting shorts";
    txt("fl-flow-kicker", k);
    txt("fl-longs", money(ln, true));
    txt("fl-shorts", money(sn, true));
    txt("fl-flow-sentence", w.smart_sentence + " Window: " + stamp(ws.base_ms) + " to " + stamp(ws.end_ms) + ", " + ws.steps + " snapshot step" + (ws.steps === 1 ? "" : "s") + ".");
    var f = ws.flows;
    tb.innerHTML = "";
    var th = mk("thead", null, null, tb), tr = mk("tr", null, null, th);
    ["USD", "Opened", "Added", "Closed", "Trimmed", "Net"].forEach(function (h) { var c = mk("th", null, h, tr); c.scope = "col"; });
    var body = mk("tbody", null, null, tb);
    [["Longs", f.oL, f.aL, f.cL, f.tL, ln], ["Shorts", f.oS, f.aS, f.cS, f.tS, sn]].forEach(function (r) {
      var row = mk("tr", null, null, body);
      var h = mk("th", null, r[0], row); h.scope = "row";
      mk("td", null, signedCell(r[1]), row);
      mk("td", null, signedCell(r[2]), row);
      mk("td", null, r[3] > 500 ? "−" + cell(r[3]) : "0", row);
      mk("td", null, r[4] > 500 ? "−" + cell(r[4]) : "0", row);
      mk("td", "net", signedCell(r[5]), row);
    });
  }

  // ------------------------------------------------------------- cohorts
  function splitBar(parent, share) {
    var bar = mk("div", "stack-rule fl-split", null, parent);
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", num(share) ? pct(1 - share, 1) + " long, " + pct(share, 1) + " short" : "no open positions");
    var l = mk("div", "long", null, bar), s = mk("div", "short", null, bar);
    l.style.width = num(share) ? ((1 - share) * 100).toFixed(2) + "%" : "0%";
    s.style.width = num(share) ? (share * 100).toFixed(2) + "%" : "0%";
    return bar;
  }

  function cohortBlock(id, name, def, w, now, headline) {
    var box = $(id);
    box.innerHTML = "";
    mk("p", "fl-k", name, box);
    mk("p", "fl-t fl-def", def, box);
    if (!w || !w.available) {
      mk("p", "fl-headline", (w && w.reason) || "Building history.", box);
      var nowp = mk("p", "fl-t", "Now: " + pct(now.short_share, 1) + " short, " + (now.members || 0) + " wallets.", box);
      splitBar(box, now.short_share);
      return;
    }
    mk("p", "fl-headline", headline, box);
    var tl = w.toward_long;
    mk("p", "fl-mid mono", Math.abs(tl) < 1 ? "No net change" : "toward " + (tl > 0 ? "LONG " : "SHORT ") + money(Math.abs(tl)), box);
    mk("p", "fl-t mono", pct(w.short_share_before, 1) + " short → " + pct(w.short_share_after, 1) + " short", box);
    splitBar(box, w.short_share_after);
    mk("p", "fl-t", w.wallets_traded + " wallet" + (w.wallets_traded === 1 ? "" : "s") + " traded · since " + clock(w.base_ms), box);
  }

  function cohorts(t) {
    var w = W() || {};
    var cs = t.cohorts || {};
    txt("fl-compare", w.compare || "Building history.");
    cohortBlock("fl-c-smart", "Top cohort", cs.smart ? cs.smart.definition : "", w.smart, cs.smart || {}, w.smart_headline);
    cohortBlock("fl-c-contrast", "Worst-performing cohort", cs.contrast ? cs.contrast.definition : "", w.contrast, cs.contrast || {}, w.contrast_headline);
    diverge(w);
  }

  function diverge(w) {
    var box = $("chart-diverge");
    var rowsD = [["Top cohort", w.smart], ["Worst-performing cohort", w.contrast]];
    if (!rowsD.some(function (r) { return r[1] && r[1].available; })) { H.empty(box, "Building history for this window."); return; }
    var s = H.surface(box, "Fig. F2. Net move toward long or short by cohort.");
    var padX = 8, top = 22, rowH = 44, bh = 12;
    var mid = Math.round(s.w / 2);
    var m = 1;
    rowsD.forEach(function (r) { if (r[1] && r[1].available) m = Math.max(m, Math.abs(r[1].toward_long)); });
    var half = s.w / 2 - padX - 60;
    H.text(s.svg, padX, 10, "← toward short", { size: 9, font: "IBM Plex Sans, sans-serif" });
    H.text(s.svg, s.w - padX, 10, "toward long →", { size: 9, anchor: "end", font: "IBM Plex Sans, sans-serif" });
    rowsD.forEach(function (r, i) {
      var y = top + i * rowH;
      H.text(s.svg, padX, y + 8, r[0], { size: 10, font: "IBM Plex Sans, sans-serif", fill: C.ink });
      var w0 = r[1], yb = y + 16;
      if (!w0 || !w0.available) {
        H.text(s.svg, mid + 6, yb + 10, "building history", { size: 9 });
        return;
      }
      var v = w0.toward_long;
      var len = Math.abs(v) / m * half;
      H.el("rect", { x: v >= 0 ? mid : mid - len, y: yb, width: Math.max(0.8, len), height: bh, fill: v >= 0 ? C.ink : C.paper, stroke: C.ink, "stroke-width": 1 }, s.svg);
      H.text(s.svg, v >= 0 ? mid + len + 5 : mid - len - 5, yb + 10, money(v, true), { size: 10, anchor: v >= 0 ? "start" : "end", fill: C.ink });
    });
    H.line(s.svg, mid, top + 12, mid, top + rowH * 2 + 2, C.accent, 1.5);
  }

  // ------------------------------------------------------------- whale tape
  function bars(parent, e) {
    var wrap = mk("div", "fl-bars", null, parent);
    var m = Math.max(e.before_usd || 0, e.now_usd || 0, 1);
    [["Before", e.before_usd, e.before_side, false], ["Now", e.now_usd, e.now_usd > 0 ? e.side : "FLAT", true]].forEach(function (r) {
      var row = mk("div", "fl-bar-row", null, wrap);
      mk("span", "fl-bar-k", r[0], row);
      var track = mk("span", "fl-bar-track", null, row);
      var b = mk("span", "fl-bar " + (r[3] ? "is-now" : "is-before"), null, track);
      b.style.width = ((r[1] || 0) / m * 100).toFixed(1) + "%";
      mk("span", "fl-bar-v mono", money(r[1]) + (r[1] > 0 ? " " + r[2] : ""), row);
    });
  }

  function fact(dl, k, v, node) {
    var d = mk("div", null, null, dl);
    mk("dt", null, k, d);
    var dd = mk("dd", "mono", node ? null : v, d);
    if (node) dd.appendChild(node);
  }

  function whaleEntry(ul, e) {
    var li = mk("li", "fl-entry", null, ul);
    var meta = mk("p", "fl-meta mono", null, li);
    meta.textContent = "BTC · " + ago(e.t) + " · " + clock(e.t);
    var rk = mk("span", "fl-rank", cohortName(e.cohort) + (e.rank ? ", rank " + e.rank + " of " + e.rank_of : ""), meta);
    var what = mk("p", "fl-what", null, li);
    var dl;
    if (e.kind === "position") {
      var verb = e.verb.charAt(0).toUpperCase() + e.verb.slice(1);
      if (e.verb === "added to" || e.verb === "trimmed") what.textContent = verb + " " + money(e.change_usd) + (e.verb === "trimmed" ? " from" : "") + " a " + e.side;
      else if (e.verb === "flipped to") what.textContent = "Flipped from " + e.before_side + " to " + e.side + ", " + money(e.change_usd) + " traded";
      else what.textContent = verb + " a " + money(e.verb === "closed" ? e.before_usd : e.now_usd) + " " + e.side;
      bars(li, e);
      dl = mk("dl", "fl-facts", null, li);
      var replayed = e.src === "git";
      if (e.now_usd > 0 && !replayed) {
        fact(dl, "Leverage", num(e.leverage) ? e.leverage + "× " + (e.leverage_type || "") : "—");
        fact(dl, "Margin", money(e.margin_usd));
      }
      fact(dl, e.px_source === "fills" ? (e.verb === "trimmed" || e.verb === "closed" ? "Cut at" : "Filled at") : "Mark at snapshot", px(e.px_source === "fills" ? e.px : e.mark));
      if (e.now_usd > 0 && !replayed) fact(dl, "PnL on margin", num(e.roe) ? spct(e.roe, 1) + " (" + money(e.upnl_usd, true) + ")" : money(e.upnl_usd, true));
      if (replayed) mk("p", "fl-t fl-note", "Replayed from snapshots stored before the tape existed; fill price, leverage, and margin were not recorded.", li);
      if (e.worked) {
        mk("p", "fl-worked", "Worked as " + e.worked.orders + " orders over " + Math.round(e.worked.minutes) + " min (" +
          (e.worked.method || (e.worked.kind === "native" ? "native TWAP" : "TWAP-like pattern")) + "), average " + px(e.worked.vwap) + ".", li);
      }
    } else if (e.kind === "worked") {
      what.textContent = (e.side === "BUY" ? "Bought " : "Sold ") + money(e.ntl) + " in " + e.orders + " orders over " + Math.round(e.minutes) + " min";
      dl = mk("dl", "fl-facts", null, li);
      fact(dl, "Method", e.method);
      if (e.effect) fact(dl, "Effect", e.effect.toLowerCase());
      fact(dl, "Average price", px(e.vwap));
      fact(dl, "Typical gap", num(e.median_gap_min) ? e.median_gap_min.toFixed(1) + " min" : "—");
      fact(dl, "Largest order", pct(e.max_share, 0) + " of total");
      fact(dl, "Taker fills", pct(e.taker_share, 0));
      fact(dl, "Window", clock(e.t0).replace(" IST", "") + "–" + clock(e.t1));
      if (num(e.pos_usd_now)) fact(dl, "Position now", money(e.pos_usd_now) + " " + (e.pos_side_now || ""));
    } else {
      what.textContent = "One order " + (e.side === "BUY" ? "bought " : "sold ") + money(e.ntl) + " at " + px(e.px);
      dl = mk("dl", "fl-facts", null, li);
      fact(dl, "Direction", e.dir || "—");
      fact(dl, "Fills", String(e.fills));
      fact(dl, "Execution", e.taker ? "crossed the book (taker)" : "resting order (maker)");
    }
    fact(dl, "All-time PnL", money(e.all_time_pnl, true));
    fact(dl, "30d PnL", money(e.month_pnl, true));
    fact(dl, "Wallet", null, link(e.address));
  }

  function tape(t) {
    var ul = $("fl-tape");
    ul.innerHTML = "";
    var list = (t.whales || []).filter(function (e) { return S.filter === "all" || e.cohort === S.filter; });
    if (!list.length) {
      mk("li", "fl-empty", S.filter === "all" ? "No whale moves recorded yet. Entries appear when a tracked wallet changes its BTC position by at least " + money((t.whale_rules || {}).position_usd) + " between snapshots, or works a large order." : "No entries for this cohort yet.", ul);
    }
    list.slice(0, 20).forEach(function (e) { whaleEntry(ul, e); });
    var r = t.whale_rules || {};
    txt("fl-tape-rule", "Rules: position change of at least " + money(r.position_usd) + " between snapshots; a single order of at least " + money(r.order_usd) +
      "; a worked order of at least " + money(r.worked_usd) + " in " + r.worked_orders + " or more same-side orders over at least " + r.worked_minutes +
      " minutes, no order above " + pct(r.worked_max_share, 0) + " of the total and no pause above " + r.worked_max_gap_min + " minutes. Kept for 7 days.");
    Array.prototype.forEach.call($("fl-wf").querySelectorAll("button"), function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-f") === S.filter ? "true" : "false");
    });
  }

  // ------------------------------------------------------------- liquidations
  function liqs(t) {
    var L = t.liquidations || {};
    var w = L.wave || {};
    var el = $("fl-wave");
    var status = w.status || "—";
    el.textContent = status + (w.wave && w.dominant_side ? " · " + w.dominant_side + "S LIQUIDATED" : "");
    el.className = "big-read" + (w.wave || w.proxy_flag ? " is-alert" : "");
    var norm = num(w.norm_hourly_usd) ? money(w.norm_hourly_usd) + " an hour" : "not yet measured (needs an hour of observation)";
    txt("fl-wave-t", "Last hour: " + money(w.last_hour_usd) + " seen in " + (w.last_hour_events || 0) + " liquidation" + (w.last_hour_events === 1 ? "" : "s") +
      " (longs " + money(w.last_hour_long_usd) + ", shorts " + money(w.last_hour_short_usd) + "). Recent norm: " + norm +
      ". A wave needs at least " + money(w.threshold_usd) + " in one hour and three or more liquidations. Seen in the last 7 days: " +
      (L.count_7d || 0) + " liquidations, " + money(L.usd_7d) + ", over " + (w.observed_hours || 0) + " hours of observation.");
    liqChart(L, w);
    var tb = $("fl-liq-table");
    var ev = (L.events || []).slice().sort(function (a, b) { return b.ntl - a.ntl; }).slice(0, 12);
    tb.innerHTML = "";
    if (!ev.length) {
      tb.innerHTML = "<tbody><tr><td>No BTC liquidations seen in tracked wallets' fills yet.</td></tr></tbody>";
    } else {
      var th = mk("thead", null, null, tb), tr = mk("tr", null, null, th);
      ["Time", "Side", "Seen", "Price", "Wallet"].forEach(function (h) { var c = mk("th", null, h, tr); c.scope = "col"; });
      var body = mk("tbody", null, null, tb);
      ev.forEach(function (e) {
        var row = mk("tr", null, null, body);
        mk("td", null, clock(e.t).replace(" IST", ""), row);
        mk("td", null, e.side, row);
        mk("td", null, money(e.ntl), row);
        mk("td", null, px(e.px), row);
        var c = mk("td", null, null, row);
        c.appendChild(link(e.user));
        if (e.tracked) mk("span", "fl-tag", e.cohort === "smart" ? " top" : " worst", c);
      });
    }
    txt("fl-liq-cap", "Table F2. Largest BTC liquidations seen in the last 7 days, times in IST. Side is the side that was liquidated. Seen is the notional that " +
      "passed through tracked wallets' fills, so the full liquidation can be larger. A tag marks a liquidated wallet that is itself in a tracked cohort.");
    var P = L.oi_proxy || {};
    var lt = P.latest;
    var s = "";
    if (!P.available || !lt) s = "Not enough stored open-interest steps yet.";
    else {
      s = "Latest step: open interest " + spct(lt.d_oi, 2) + ", price " + spct(lt.ret, 2) + (lt.flag ? ". Flagged as a possible liquidation burst, up to " + money(lt.usd) + " of " + (lt.ret < 0 ? "longs" : "shorts") + "." : ". Not flagged.");
      var fl = P.flagged || [];
      s += " Flagged steps in 7 days: " + fl.length + (fl.length ? " (latest " + stamp(fl[fl.length - 1].t) + ", " + (fl[fl.length - 1].side === "LONG" ? "longs" : "shorts") + ", up to " + money(fl[fl.length - 1].usd) + ")." : ".");
      s += " Rule: " + P.rule;
    }
    txt("fl-proxy", s);
  }

  function liqChart(L, w) {
    var box = $("chart-liqs");
    var hs = L.hourly || [];
    var since = L.observing_since_ms ? Math.floor(L.observing_since_ms / 3600000) * 3600000 : 0;
    var cut = hs.filter(function (h) { return h[0] >= since; });
    hs = cut.length >= 6 ? cut : hs.slice(-6);
    if (!hs.length) { H.empty(box, "No hourly data yet."); return; }
    var any = hs.some(function (h) { return h[1] > 0 || h[2] > 0; });
    var s = H.surface(box, "Fig. F3. Hourly liquidated notional seen.");
    var padL = 40, padR = 6, padT = 8, padB = 20;
    var m = Math.max(1, w.threshold_usd || 0);
    hs.forEach(function (h) { m = Math.max(m, h[1], h[2]); });
    var mid = padT + (s.h - padT - padB) / 2;
    var yUp = H.scale(0, m, mid, padT), yDn = H.scale(0, m, mid, s.h - padB);
    var t0 = hs[0][0], t1 = hs[hs.length - 1][0] + 3600000;
    var x = H.scale(t0, t1, padL, s.w - padR);
    var bw = Math.max(1, (s.w - padL - padR) / hs.length - 1);
    H.text(s.svg, padL - 4, padT + 8, "longs", { size: 9, anchor: "end", font: "IBM Plex Sans, sans-serif" });
    H.text(s.svg, padL - 4, s.h - padB - 2, "shorts", { size: 9, anchor: "end", font: "IBM Plex Sans, sans-serif" });
    H.text(s.svg, padL - 4, yUp(m) + 18, H.fmtK(m), { size: 9, anchor: "end" });
    if (w.threshold_usd) {
      H.line(s.svg, padL, yUp(w.threshold_usd), s.w - padR, yUp(w.threshold_usd), C.muted, 1, "3 3");
      H.line(s.svg, padL, yDn(w.threshold_usd), s.w - padR, yDn(w.threshold_usd), C.muted, 1, "3 3");
    }
    hs.forEach(function (h) {
      var xx = x(h[0]);
      if (h[1] > 0) H.el("rect", { x: xx, y: yUp(h[1]), width: bw, height: Math.max(0.8, mid - yUp(h[1])), fill: C.ink }, s.svg);
      if (h[2] > 0) H.el("rect", { x: xx + 0.5, y: mid, width: Math.max(0.5, bw - 1), height: Math.max(0.8, yDn(h[2]) - mid), fill: C.paper, stroke: C.ink, "stroke-width": 1 }, s.svg);
    });
    H.line(s.svg, padL, mid, s.w - padR, mid, C.ink, 1);
    if (!any) H.text(s.svg, padL + 6, mid - 6, s.w < 520 ? "None seen in this period." : "No liquidations seen in tracked wallets' fills in this period.", { size: 10 });
    H.line(s.svg, padL, s.h - padB, s.w - padR, s.h - padB, C.hair, 1);
    H.timeAxis(s.svg, x, t0, t1, s.h - padB, s.w < 500 ? 2 : 4, false);
  }

  function limits(t) {
    var ul = $("fl-limits");
    ul.innerHTML = "";
    (t.limits || []).forEach(function (s) { mk("li", null, s, ul); });
  }

  function render() {
    var t = T();
    var st = $("fl-status");
    if (!S.data) return;
    txt("fl-issued", "Snapshot issued " + (S.data.ts_ist || "—") + ".");
    if (!t) {
      st.hidden = false;
      st.textContent = "This snapshot predates the flow tracker. It appears after the next sweep.";
      return;
    }
    st.hidden = true;
    var steps = [timeframes, reading, flowBox, cohorts, tape, liqs, limits];
    steps.forEach(function (fn) {
      try { fn(t); } catch (err) { if (window.console) console.warn("flows panel failed", err); }
    });
  }

  function boot() {
    var wf = $("fl-wf");
    if (wf) wf.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("button[data-f]") : null;
      if (!b) return;
      S.filter = b.getAttribute("data-f");
      var t = T();
      if (t) tape(t);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();

  var timer = null;
  window.addEventListener("resize", function () {
    var p = $("panel-flows");
    if (!p || p.hidden) return;
    clearTimeout(timer);
    timer = setTimeout(render, 150);
  });

  window.renderFlows = function (data) {
    if (data) S.data = data;
    render();
  };
})();
