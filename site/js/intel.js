/* Market-intelligence panels. Reads data.intel (signal.json) and history.json. */
(function () {
  "use strict";
  var H = window.HLCharts;
  var C = H.C;
  var state = { data: null, history: [] };

  function $(id) { return document.getElementById(id); }
  function num(x) { return x != null && !isNaN(x); }
  function f(x, d) { return num(x) ? Number(x).toFixed(d == null ? 3 : d) : "—"; }
  function pct(x, d, signed) {
    if (!num(x)) return "—";
    var v = (x * 100).toFixed(d == null ? 1 : d);
    return (signed && x > 0 ? "+" : "") + v.replace("-", "−") + "%";
  }
  function money(x) {
    if (!num(x)) return "—";
    var a = Math.abs(x), s = x < 0 ? "−" : "";
    if (a >= 1e9) return s + "$" + (a / 1e9).toFixed(2) + "b";
    if (a >= 1e6) return s + "$" + (a / 1e6).toFixed(2) + "m";
    if (a >= 1e3) return s + "$" + (a / 1e3).toFixed(1) + "k";
    return s + "$" + a.toFixed(0);
  }
  function px(x) { return num(x) ? Number(x).toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—"; }
  function addr(a) { return a && a.length > 12 ? a.slice(0, 6) + "…" + a.slice(-4) : (a || "—"); }

  function rows(id, data, header) {
    var t = $(id);
    if (!t) return;
    t.innerHTML = "";
    if (header) {
      var th = document.createElement("thead"), tr = document.createElement("tr");
      header.forEach(function (h) { var c = document.createElement("th"); c.scope = "col"; c.textContent = h; tr.appendChild(c); });
      th.appendChild(tr); t.appendChild(th);
    }
    var tb = document.createElement("tbody");
    data.forEach(function (r) {
      var tr = document.createElement("tr");
      r.forEach(function (c, i) {
        var td = document.createElement(i === 0 && !header ? "th" : "td");
        if (i === 0 && !header) td.scope = "row";
        if (c && typeof c === "object" && c.flag != null) {
          td.textContent = c.text;
          if (c.flag) td.className = "flag";
        } else td.textContent = c == null ? "—" : c;
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    t.appendChild(tb);
  }

  function msOf(ts) { var t = Date.parse(ts); return isNaN(t) ? null : t; }

  // ---------------------------------------------------------------- readout
  function readout(d, I) {
    var age = d.ts_utc ? (Date.now() - Date.parse(d.ts_utc)) / 1000 : 0;
    var integ = I.integrity || {};
    var status = integ.status || "—";
    if (age > 7200 && status === "CLEAN") status = "CAUTION";
    var fr = I.front_running || {};
    var risk = I.risk || {};
    var fg = I.fear_greed || {};
    var reg = I.regime || {};
    var contra = I.contrarian || {};
    var watch = I.market_watch || {};
    var b = I.bayes || {};
    var data = [
      ["Market change watch", watch.level || "—", watch.summary || ""],
      ["Flip detector", (I.flip || {}).status || "—", (I.flip || {}).text || ""],
      ["Posterior P(long)", b.available ? f(b.posterior_mean) + "  [" + f(b.ci_low) + ", " + f(b.ci_high) + "]" : "—",
        b.available ? "Raw " + f(b.raw_p) + "; the posterior forgets older sweeps with a " + b.half_life_h + "-hour half-life." : ""],
      ["Cohort risk grade", risk.available ? risk.aggregate_grade + "  squeeze " + (risk.squeeze || {}).level : "—",
        risk.available ? (risk.squeeze || {}).text : (risk.reason || "")],
      ["Regime", reg.label ? reg.label + (reg.sub ? " (" + reg.sub + ")" : "") : "—", reg.detail || ""],
      ["Fear and greed", fg.available ? fg.score.toFixed(0) + "  " + fg.band : "—",
        fg.available ? fg.components.length + " components; " + (fg.missing.length ? "awaiting " + fg.missing.join(", ").toLowerCase() + "." : "all present.") : ""],
      ["Signal integrity", status + (integ.n_flags != null ? "  " + integ.n_flags + " flag" + (integ.n_flags === 1 ? "" : "s") : ""),
        integ.checks ? integ.checks.filter(function (c) { return c.flag; }).map(function (c) { return c.name.toLowerCase(); }).join(", ") || "No checks flagged." : ""],
      ["Funding", num((I.funding_oi || {}).funding_ann) ? pct(I.funding_oi.funding_ann, 1, true) + " a year" : "—", (I.funding_oi || {}).reading || ""],
      ["Contrarian", contra.faded_verdict ? "fade = " + contra.faded_verdict : "—", contra.text || ""],
      ["Front-running meter", fr.label || "—", fr.score != null ? "Lead score " + f(fr.score, 2) + " from " + (fr.source || "") + " (n = " + fr.n + ")." : "Not enough paired observations yet."]
    ];
    var t = $("board");
    t.innerHTML = "";
    var tb = document.createElement("tbody");
    data.forEach(function (r) {
      var tr = document.createElement("tr");
      var th = document.createElement("th"); th.scope = "row"; th.textContent = r[0]; tr.appendChild(th);
      var v = document.createElement("td"); v.className = "val"; v.textContent = r[1]; tr.appendChild(v);
      var w = document.createElement("td"); w.className = "why"; w.textContent = r[2]; tr.appendChild(w);
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    if ($("posterior")) $("posterior").textContent = b.available ? f(b.posterior_mean) : "—";
    if ($("integrity-mini")) $("integrity-mini").textContent = status;
    if ($("flip-mini")) $("flip-mini").textContent = (I.flip || {}).status || "—";
  }

  // ---------------------------------------------------------------- history
  function history(d, hist) {
    var pts = hist.filter(function (h) { return h.p_long != null; });
    var note = $("history-note");
    if (pts.length < 2) {
      note.hidden = false;
      note.textContent = pts.length === 1 ? "One snapshot stored; the chart fills as later sweeps arrive." : "No stored history yet.";
    } else note.hidden = true;
    var T = function (h) { return msOf(h.ts_utc); };
    H.timeseries($("chart-history"), [
      { pts: hist.map(function (h) { return [T(h), h.btc_mark]; }), axis: "right", stroke: C.grey, width: 1 },
      { pts: hist.map(function (h) { return [T(h), h.post]; }), stroke: C.ink, width: 1, dash: "4 3" },
      { pts: pts.map(function (h) { return [T(h), h.p_long]; }), stroke: C.accent, width: 1.6, dots: pts.length < 40 }
    ], {
      label: "Fig. 2. History of P(long), posterior, and BTC mark.",
      leftDomain: [0, 1], leftTicks: [0, 0.4, 0.5, 0.6, 1], leftFmt: function (v) { return v.toFixed(1); },
      leftRefs: [[0.5, C.ink], [0.4, C.hair, "2 3"], [0.6, C.hair, "2 3"]],
      rightLabels: true, rightFmt: function (v) { return v.toLocaleString("en-US", { maximumFractionDigits: 0 }); }, gapMs: 3 * 3600 * 1000
    });
  }

  // ---------------------------------------------------------------- price + EMA
  function priceAction(d, I) {
    var ch = I.chart || {};
    H.candles($("chart-price"), ch.candles_1h, ch.ema_1h, { mark: d.btc_mark, label: "Fig. 4. BTC hourly candles with EMA 20, 50, 200." });
    H.candles($("chart-daily"), ch.candles_1d, ch.ema_1d, { compact: true, daily: true, label: "BTC daily candles with EMAs." });
    var pa = I.price_action || {}, e1 = (I.ema || {}).h1 || {}, e2 = (I.ema || {}).d1 || {};
    function cross(c) { return c ? c.kind + ", " + H.fmtTime(c.t, false) : "none in window"; }
    rows("pa-table", [
      ["Return 1h / 4h", pct(pa.ret_1h, 2, true) + " / " + pct(pa.ret_4h, 2, true)],
      ["Return 24h / 7d", pct(pa.ret_24h, 1, true) + " / " + pct(pa.ret_7d, 1, true)],
      ["Return 30d", pct(pa.ret_30d, 1, true)],
      ["24h range", px(pa.low_24h) + " – " + px(pa.high_24h)],
      ["7d range (position)", px(pa.low_7d) + " – " + px(pa.high_7d) + " (" + pct(pa.pos_in_7d_range, 0) + ")"],
      ["1h vs EMA 20/50/200", pct(e1.dist_ema20, 1, true) + " / " + pct(e1.dist_ema50, 1, true) + " / " + pct(e1.dist_ema200, 1, true)],
      ["1h stack", e1.state || "—"],
      ["1h last 20/50 cross", cross(e1.cross_20_50)],
      ["1d vs EMA 50/200", pct(e2.dist_ema50, 1, true) + " / " + pct(e2.dist_ema200, 1, true)],
      ["1d stack", e2.state || "—"],
      ["1d last 50/200 cross", cross(e2.cross_50_200)]
    ]);
  }

  // ---------------------------------------------------------------- regime + fear/greed
  function regimeFG(d, I) {
    var r = I.regime || {};
    $("regime-label").textContent = r.label ? r.label + (r.sub ? " · " + r.sub : "") : "—";
    $("regime-detail").textContent = (r.detail || "") + (r.funding_note ? " " + r.funding_note : "");
    rows("regime-table", [
      ["Realised vol 24h, annualised", pct(r.rv_24h_ann, 0)],
      ["Vol percentile, 30 days", pct(r.rv_pct_30d, 0)],
      ["Efficiency ratio, 48h", f(r.efficiency_ratio_48h, 2)],
      ["EMA 50 slope, 24h", pct(r.ema50_slope_24h, 2, true)],
      ["Funding, annualised", pct(r.funding_ann, 1, true)]
    ]);
    var fg = I.fear_greed || {};
    H.meter($("chart-fg"), fg.available ? fg.score : null, {
      lo: 0, hi: 100, bands: [[25], [45], [55], [75]],
      ticks: [[0, "0 fear"], [25, "25"], [50, "50"], [75, "75"], [100, "greed 100"]],
      valueFmt: function (v) { return v.toFixed(0) + " " + (fg.band || "").toLowerCase(); },
      label: "Fear and greed meter"
    });
    rows("fg-table", (fg.components || []).map(function (c) { return [c.name, c.score.toFixed(0), c.note]; })
      .concat((fg.missing || []).map(function (m) { return [m, "—", "Awaiting stored history."]; })), ["Component", "Score", "Basis"]);
  }

  // ---------------------------------------------------------------- liquidation map
  function liqMap(d, I) {
    var L = I.liquidation_map || {};
    var box = $("chart-liq");
    if (!L.available) { H.empty(box, "No liquidation data."); return; }
    var s = H.surface(box, "Fig. 6. Liquidation map.");
    var padL = 44, padR = 8, padT = 18, padB = 22;
    var bins = L.bins;
    var mx = 0;
    bins.forEach(function (b) { mx = Math.max(mx, b.long_ntl, b.short_ntl); });
    if (!mx) mx = 1;
    var x = H.scale(-L.span_pct, L.span_pct, padL, s.w - padR);
    var y = H.scale(0, mx, s.h - padB, padT);
    H.niceTicks(0, mx, 3).forEach(function (v) {
      H.line(s.svg, padL, y(v), s.w - padR, y(v), C.hair, 0.6, "1 3");
      H.text(s.svg, padL - 4, y(v) + 3, "$" + H.fmtK(v), { anchor: "end", size: 9 });
    });
    bins.forEach(function (b) {
      var x0 = x(b.lo_pct) + 0.5, w = Math.max(1, x(b.hi_pct) - x(b.lo_pct) - 1);
      if (b.long_ntl > 0) H.el("rect", { x: x0, y: y(b.long_ntl), width: w, height: s.h - padB - y(b.long_ntl), fill: C.ink }, s.svg);
      if (b.short_ntl > 0) H.el("rect", { x: x0 + 0.5, y: y(b.short_ntl), width: w - 1, height: s.h - padB - y(b.short_ntl) - 0.5, fill: "none", stroke: C.ink, "stroke-width": 1 }, s.svg);
    });
    H.line(s.svg, padL, s.h - padB, s.w - padR, s.h - padB, C.ink, 1);
    H.line(s.svg, x(0), padT - 6, x(0), s.h - padB, C.accent, 1.5);
    H.text(s.svg, x(0) + 3, padT, "mark " + px(L.mark), { size: 9, fill: C.accent });
    var step = s.w < 500 ? 10 : 5;
    for (var p = -L.span_pct; p <= L.span_pct; p += step) {
      H.line(s.svg, x(p), s.h - padB, x(p), s.h - padB + 3, C.ink, 1);
      H.text(s.svg, x(p), s.h - padB + 13, (p > 0 ? "+" : "") + p + "%" + (s.w > 700 ? " " + H.fmtK(L.mark * (1 + p / 100)) : ""), { anchor: "middle", size: 9 });
    }
    var parts = [
      money(L.shorts_liq_within_5pct_up) + " of short notional liquidates within 5% above the mark (" + money(L.shorts_liq_within_10pct_up) + " within 10%).",
      money(L.longs_liq_within_5pct_down) + " of long notional liquidates within 5% below (" + money(L.longs_liq_within_10pct_down) + " within 10%)."
    ];
    if (L.peak_above) parts.push("Largest cluster above: " + money(L.peak_above.ntl) + " near " + px(L.peak_above.price) + ".");
    if (L.peak_below) parts.push("Largest cluster below: " + money(L.peak_below.ntl) + " near " + px(L.peak_below.price) + ".");
    var nl = (L.no_liq_px || {});
    parts.push("Outside ±" + L.span_pct + "%: " + money((L.beyond || {}).long_ntl + (L.beyond || {}).short_ntl) + "; no liquidation price reported: " + money(nl.long_ntl + nl.short_ntl) + ".");
    $("liq-note").textContent = parts.join(" ");
  }

  // ---------------------------------------------------------------- funding + OI
  function fundingOI(d, I, hist) {
    var F = I.funding_oi || {};
    var ser = F.series_8h || [];
    var box = $("chart-funding");
    if (!ser.length) H.empty(box, "No funding history.");
    else {
      var s = H.surface(box, "Funding, 8-hour means, annualised.");
      var padL = 40, padR = 8, padT = 8, padB = 20;
      var ex = H.extent(ser.map(function (r) { return r.ann; }).concat([0]));
      var y = H.scale(ex[0], ex[1], s.h - padB, padT);
      var t0 = ser[0].t, t1 = ser[ser.length - 1].t + 8 * 3600e3;
      var x = H.scale(t0, t1, padL, s.w - padR);
      H.niceTicks(ex[0], ex[1], 4).forEach(function (v) {
        H.line(s.svg, padL, y(v), s.w - padR, y(v), C.hair, 0.6, "1 3");
        H.text(s.svg, padL - 4, y(v) + 3, (v * 100).toFixed(0) + "%", { anchor: "end", size: 9 });
      });
      var bw = Math.max(1, (s.w - padL - padR) / ser.length - 1);
      ser.forEach(function (r) {
        var y0 = y(0), y1 = y(r.ann);
        H.el("rect", { x: x(r.t), y: Math.min(y0, y1), width: bw, height: Math.max(0.8, Math.abs(y1 - y0)), fill: r.ann >= 0 ? C.ink : "none", stroke: C.ink, "stroke-width": r.ann >= 0 ? 0 : 0.8 }, s.svg);
      });
      H.line(s.svg, padL, y(0), s.w - padR, y(0), C.ink, 1);
      H.timeAxis(s.svg, x, t0, t1, s.h - padB, s.w < 500 ? 2 : 4, true);
    }
    var T = function (h) { return msOf(h.ts_utc); };
    var oiPts = hist.filter(function (h) { return h.oi != null && h.btc_mark != null; }).map(function (h) { return [T(h), h.oi * h.btc_mark]; });
    H.timeseries($("chart-oi"), [
      { pts: oiPts, stroke: C.ink, width: 1.2, dots: oiPts.length < 40 },
      { pts: hist.filter(function (h) { return h.oi != null; }).map(function (h) { return [T(h), h.p_long]; }), axis: "right", stroke: C.accent, width: 1 }
    ], { label: "Open interest from stored sweeps.", leftFmt: function (v) { return "$" + H.fmtK(v); }, emptyMsg: "Open interest is stored from this release on; the line fills with later sweeps.", rightLabels: true, rightFmt: function (v) { return v.toFixed(2); }, gapMs: 3 * 3600e3 });
    rows("fo-table", [
      ["Funding now, hourly", num(F.funding_rate_h) ? (F.funding_rate_h * 100).toFixed(4) + "%" : "—"],
      ["Annualised", pct(F.funding_ann, 1, true)],
      ["7-day mean, annualised", pct(F.funding_ann_avg_7d, 1, true)],
      ["Percentile, 30 days", pct(F.funding_pct_30d, 0)],
      ["Open interest", num(F.oi_btc) ? F.oi_btc.toLocaleString("en-US", { maximumFractionDigits: 0 }) + " BTC" : "—"],
      ["Open interest, USD", money(F.oi_usd)],
      ["OI change, 24h", num(F.oi_change_24h) ? pct(F.oi_change_24h, 1, true) : "awaiting 24h of sweeps"],
      ["Premium to oracle", num(F.premium) ? pct(F.premium, 3, true) : "—"],
      ["24h notional volume", money(F.day_ntl_vlm)]
    ]);
    $("fo-reading").textContent = F.reading || "";
  }

  // ---------------------------------------------------------------- flips + feed
  function flips(d, I) {
    var fl = I.flip || {}, ch = I.changes || {}, w = I.market_watch || {};
    $("flip-label").textContent = (fl.status || "—") + "  ·  market watch " + (w.level || "—");
    $("flip-text").textContent = (fl.text || "") + " " + (w.summary || "");
    var ul = $("watch-list");
    ul.innerHTML = "";
    (w.signals || []).forEach(function (sig) { var li = document.createElement("li"); li.textContent = sig; ul.appendChild(li); });
    if (!ch.available) {
      rows("feed-table", [["Baseline stored. The feed lists changes from the next sweep."]]);
      return;
    }
    var c = ch.counts || {};
    $("feed-caption").textContent = "Fig. 8. Position-change feed since " + (ch.since_utc ? H.fmtTime(Date.parse(ch.since_utc)) + " IST" : "the previous sweep") +
      ": " + c.OPEN + " opens, " + c.CLOSE + " closes, " + c.FLIP + " flips, " + c.ADD + " adds, " + c.CUT + " cuts; net notional flow across all compared wallets, small changes included, " + money(ch.net_notional_flow) +
      ". Cohort churn: " + ch.cohort_churn_in + " in, " + ch.cohort_churn_out + " out (not counted). Adds and cuts under 10% or $50k are omitted.";
    if (!ch.feed || !ch.feed.length) { rows("feed-table", [["No position changes since the previous sweep."]]); return; }
    rows("feed-table", ch.feed.map(function (r) {
      return [addr(r.address), r.kind, r.from + " → " + r.to, (r.d_btc > 0 ? "+" : "") + r.d_btc.toFixed(3), money(r.d_ntl), Math.abs(r.cur_btc).toFixed(3)];
    }), ["Address", "Change", "Side", "Δ BTC", "Δ notional", "Now (BTC)"]);
  }

  // ---------------------------------------------------------------- risk
  function risk(d, I) {
    var R = I.risk || {};
    if (!R.available) { $("risk-grade").textContent = "—"; $("squeeze-text").textContent = R.reason || ""; H.empty($("chart-risk"), "No risk data."); return; }
    $("risk-grade").textContent = "Grade " + R.aggregate_grade;
    $("risk-sub").textContent = "squeeze risk " + R.squeeze.level.toLowerCase();
    $("squeeze-text").textContent = R.squeeze.text + " Daily BTC sigma " + pct(R.sigma_daily, 2) + ". Notional-weighted effective leverage: longs " + f(R.long.lev_w, 1) + "×, shorts " + f(R.short.lev_w, 1) + "×.";
    var s = H.surface($("chart-risk"), "Fig. 9. BTC notional by risk grade.");
    var grades = ["A", "B", "C", "D", "F"];
    var padL = 18, padR = 8, padT = 8, padB = 18;
    var mx = 1;
    grades.forEach(function (g) { mx = Math.max(mx, R.distribution.LONG[g].ntl, R.distribution.SHORT[g].ntl); });
    var gw = (s.w - padL - padR) / grades.length;
    var y = H.scale(0, mx, s.h - padB, padT);
    grades.forEach(function (g, i) {
      var x0 = padL + gw * i;
      var bw = Math.min(28, gw * 0.32);
      var L = R.distribution.LONG[g], S = R.distribution.SHORT[g];
      H.el("rect", { x: x0 + gw / 2 - bw - 1, y: y(L.ntl), width: bw, height: s.h - padB - y(L.ntl), fill: C.ink }, s.svg);
      H.el("rect", { x: x0 + gw / 2 + 1.5, y: y(S.ntl), width: bw - 1, height: Math.max(0, s.h - padB - y(S.ntl) - 0.5), fill: "none", stroke: C.ink }, s.svg);
      H.text(s.svg, x0 + gw / 2, s.h - 5, g, { anchor: "middle", size: 10, fill: C.ink, font: "IBM Plex Sans, sans-serif" });
      var lab = S.ntl >= L.ntl ? S : L;
      if (lab.ntl > 0) H.text(s.svg, x0 + gw / 2, y(Math.max(L.ntl, S.ntl)) - 3, "$" + H.fmtK(L.ntl + S.ntl), { anchor: "middle", size: 9 });
    });
    H.line(s.svg, padL, s.h - padB, s.w - padR, s.h - padB, C.ink, 1);
    rows("risk-table", (R.closest_to_liq || []).map(function (r) {
      return [addr(r.address), r.side, r.grade, num(r.liq_dist) ? pct(r.liq_dist, 1) : "none", num(r.z) ? r.z.toFixed(1) + "σ" : "—", num(r.eff_lev) ? r.eff_lev.toFixed(1) + "×" : "—", money(r.ntl)];
    }), ["Address", "Side", "Grade", "To liq.", "Sigmas", "Eff. lev.", "Notional"]);
  }

  // ---------------------------------------------------------------- integrity + bayes
  function integrity(d, I) {
    var G = I.integrity || {};
    var age = d.ts_utc ? (Date.now() - Date.parse(d.ts_utc)) / 1000 : 0;
    var checks = (G.checks || []).map(function (c) {
      if (c.name === "Data age") return { name: c.name, flag: age > 7200, value: Math.round(age / 60) + " min", rule: c.rule };
      return c;
    });
    var n = checks.filter(function (c) { return c.flag; }).length;
    var status = n === 0 ? "CLEAN" : (n <= 2 ? "CAUTION" : "SUSPECT");
    $("integrity-label").textContent = status + "  ·  " + n + " of " + checks.length + " checks flagged";
    rows("integrity-table", checks.map(function (c) {
      return [c.name, c.value, { text: c.flag ? "FLAG" : "pass", flag: c.flag }, c.rule];
    }), ["Check", "Value", "", "Rule"]);
  }

  function lbeta(a, b) { return lgamma(a) + lgamma(b) - lgamma(a + b); }
  function lgamma(z) {
    var g = 7, c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
    if (z < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * z)) - lgamma(1 - z);
    z -= 1; var x = c[0];
    for (var i = 1; i < g + 2; i++) x += c[i] / (z + i);
    var t = z + g + 0.5;
    return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(x);
  }

  function bayes(d, I) {
    var B = I.bayes || {};
    var box = $("chart-bayes");
    if (!B.available) { H.empty(box, "No posterior yet."); return; }
    var s = H.surface(box, "Fig. 10. Posterior density.");
    var padL = 8, padR = 8, padT = 8, padB = 18;
    var x = H.scale(0, 1, padL, s.w - padR);
    var pts = [], mx = 0, lb = lbeta(B.alpha, B.beta);
    for (var i = 1; i < 400; i++) {
      var p = i / 400;
      var v = Math.exp((B.alpha - 1) * Math.log(p) + (B.beta - 1) * Math.log(1 - p) - lb);
      pts.push([p, v]); if (v > mx) mx = v;
    }
    var y = H.scale(0, mx, s.h - padB, padT);
    H.path(s.svg, pts.map(function (q) { return [x(q[0]), y(q[1])]; }), C.ink, 1.3);
    [0, 0.4, 0.5, 0.6, 1].forEach(function (t) {
      H.line(s.svg, x(t), s.h - padB, x(t), s.h - padB + 3, C.ink, 1);
      H.text(s.svg, x(t), s.h - 4, t.toFixed(1), { anchor: t === 0 ? "start" : (t === 1 ? "end" : "middle"), size: 9 });
    });
    H.line(s.svg, x(0.4), padT, x(0.4), s.h - padB, C.hair, 1, "2 3");
    H.line(s.svg, x(0.6), padT, x(0.6), s.h - padB, C.hair, 1, "2 3");
    if (num(B.raw_p)) { H.line(s.svg, x(B.raw_p), padT, x(B.raw_p), s.h - padB, C.accent, 1.5); H.text(s.svg, x(B.raw_p) + 3, padT + 8, "raw", { size: 9, fill: C.accent }); }
    H.line(s.svg, padL, s.h - padB, s.w - padR, s.h - padB, C.ink, 1);
    rows("bayes-table", [
      ["Posterior mean", f(B.posterior_mean)],
      ["95% credible interval", "[" + f(B.ci_low) + ", " + f(B.ci_high) + "]"],
      ["Raw P(long) this sweep", f(B.raw_p)],
      ["Raw minus posterior", num(B.gap) ? (B.gap > 0 ? "+" : "") + B.gap.toFixed(3) : "—"],
      ["P(long share > 0.5)", f(B.prob_long_side)],
      ["α, β", f(B.alpha, 2) + ", " + f(B.beta, 2)]
    ]);
  }

  // ---------------------------------------------------------------- contrarian
  var fadeView = false;
  function contrarian(d, I) {
    var K = I.contrarian || {};
    function paint() {
      $("view-crowd").setAttribute("aria-pressed", String(!fadeView));
      $("view-fade").setAttribute("aria-pressed", String(fadeView));
      var v = fadeView ? K.faded_verdict : K.verdict;
      var el = $("contra-verdict");
      el.textContent = (v || "—") + (fadeView ? "  (faded)" : "  (crowd)");
      $("contra-p").textContent = fadeView
        ? "Faded P(long) " + f(K.faded_p_long) + ". This is the leaders' reading turned over, shown for comparison."
        : "Crowd P(long) " + f(d.p_long) + (K.extreme_now ? ". The reading is in the extreme band." : ". The reading is not in the extreme band.");
    }
    $("view-crowd").onclick = function () { fadeView = false; paint(); };
    $("view-fade").onclick = function () { fadeView = true; paint(); };
    paint();
    var ev = K.evidence_n || 0;
    $("contra-text").textContent = K.text + " Scored extreme readings so far: " + ev + (num(K.fade_hit_rate_24h) ? ", fade right " + pct(K.fade_hit_rate_24h, 0) + " at 24h." : ".");
  }

  // ---------------------------------------------------------------- backtest
  function backtest(d, I) {
    var A = (I.accuracy || {}).horizons || {};
    var hz = ["1h", "4h", "24h"];
    rows("acc-table", hz.map(function (h) {
      var a = A[h] || {};
      return [h, a.n || 0, a.n_directional || 0, num(a.hit_rate) ? pct(a.hit_rate, 0) : "—", f(a.brier_raw), f(a.brier_post), "0.250", f(a.brier_climatology), a.independent_n_approx || 0, a.pending || 0];
    }), ["Horizon", "Scored", "Directional", "Hit rate", "Brier raw", "Brier post.", "Coin", "Base rate", "Indep. n≈", "Pending"]);
    var B = I.backtest;
    if (!B || !B.available) {
      H.empty($("chart-bt"), "Reconstructed backtest not built yet.");
      H.empty($("chart-bt-eq"), "");
      return;
    }
    var ser = B.series || [];
    H.timeseries($("chart-bt"), [
      { pts: ser.map(function (r) { return [r.t, r.px]; }), axis: "right", stroke: C.grey, width: 1 },
      { pts: ser.map(function (r) { return [r.t, r.p]; }), stroke: C.accent, width: 1.4 }
    ], { label: "Fig. 11. Reconstructed P(long).", leftDomain: [0, 1], leftTicks: [0, 0.4, 0.6, 1], leftFmt: function (v) { return v.toFixed(1); }, leftRefs: [[0.5, C.ink], [0.4, C.hair, "2 3"], [0.6, C.hair, "2 3"]], rightLabels: true });
    var cv = B.curve || [];
    H.timeseries($("chart-bt-eq"), [
      { pts: cv.map(function (r) { return [r.t, r.hold - 1]; }), stroke: C.grey, width: 1 },
      { pts: cv.map(function (r) { return [r.t, r.follow - 1]; }), stroke: C.ink, width: 1.4 }
    ], { label: "Follow versus hold.", leftFmt: function (v) { return (v * 100).toFixed(0) + "%"; }, leftRefs: [[0, C.hair]] });
    var S = B.scores || {};
    rows("bt-table", [
      ["Built", B.built_at_ist || "—"],
      ["Wallets (full 7-day window)", B.n_wallets + " (" + B.wallets_with_full_window + ")"],
      ["Hit rate 4h (directional n)", (num((S["4h"] || {}).hit_rate) ? pct(S["4h"].hit_rate, 0) : "—") + " (" + ((S["4h"] || {}).n_directional || 0) + ")"],
      ["Hit rate 24h (directional n)", (num((S["24h"] || {}).hit_rate) ? pct(S["24h"].hit_rate, 0) : "—") + " (" + ((S["24h"] || {}).n_directional || 0) + ")"],
      ["Brier 4h / 24h", f((S["4h"] || {}).brier) + " / " + f((S["24h"] || {}).brier)],
      ["Follow / hold, 7 days", pct(B.follow_return, 1, true) + " / " + pct(B.hold_return, 1, true)]
    ]);
    var ul = $("bt-limits");
    ul.innerHTML = "";
    (B.limits || []).forEach(function (t) { var li = document.createElement("li"); li.textContent = t; ul.appendChild(li); });
  }

  // ---------------------------------------------------------------- lead-lag
  function ccfChart(box, ll, title) {
    if (!ll || !ll.ccf || !ll.ccf.some(function (c) { return c.r != null; })) { H.empty(box, title + ": too few paired points yet."); return; }
    var s = H.surface(box, title);
    var padL = 30, padR = 8, padT = 14, padB = 18;
    var ks = ll.ccf.map(function (c) { return c.lag; });
    var kmax = Math.max.apply(null, ks);
    var x = H.scale(-kmax - 0.5, kmax + 0.5, padL, s.w - padR);
    var rmax = 0.5;
    ll.ccf.forEach(function (c) { if (c.r != null) rmax = Math.max(rmax, Math.abs(c.r)); });
    if (ll.noise_band) rmax = Math.max(rmax, ll.noise_band * 1.3);
    rmax = Math.min(1, Math.ceil(rmax * 10) / 10);
    var y = H.scale(-rmax, rmax, s.h - padB, padT);
    H.text(s.svg, padL, 9, title + " (n = " + ll.n + ")", { size: 9, fill: C.ink, font: "IBM Plex Sans, sans-serif" });
    [-rmax, 0, rmax].forEach(function (v) { H.text(s.svg, padL - 4, y(v) + 3, v === 0 ? "0" : (v > 0 ? "+" : "−") + Math.abs(v).toFixed(1), { anchor: "end", size: 9 }); });
    H.line(s.svg, padL, y(0), s.w - padR, y(0), C.ink, 1);
    if (ll.noise_band) {
      H.line(s.svg, padL, y(ll.noise_band), s.w - padR, y(ll.noise_band), C.muted, 1, "3 3");
      H.line(s.svg, padL, y(-ll.noise_band), s.w - padR, y(-ll.noise_band), C.muted, 1, "3 3");
    }
    var bw = Math.max(2, (s.w - padL - padR) / ks.length * 0.5);
    ll.ccf.forEach(function (c) {
      if (c.r == null) return;
      var isPeak = ll.peak && ll.peak.lag === c.lag;
      H.el("rect", { x: x(c.lag) - bw / 2, y: Math.min(y(0), y(c.r)), width: bw, height: Math.max(0.8, Math.abs(y(c.r) - y(0))), fill: isPeak ? C.accent : C.ink }, s.svg);
    });
    ks.forEach(function (k) { if (k % 2 === 0) H.text(s.svg, x(k), s.h - 4, (k > 0 ? "+" : "") + k, { anchor: "middle", size: 9 }); });
    H.line(s.svg, x(0), padT, x(0), s.h - padB, C.hair, 1);
  }

  function leadLag(d, I) {
    var L = I.lead_lag || {};
    ccfChart($("chart-ccf-live"), L.live, "Live, 30-min steps");
    ccfChart($("chart-ccf-bt"), L.reconstructed, "Reconstructed, hourly");
    var F = I.front_running || {};
    H.meter($("chart-fr"), F.score, {
      lo: -1, hi: 1, bands: [[-0.2], [0.2]],
      ticks: [[-1, "chasing −1"], [0, "0"], [1, "+1 front-running"]],
      valueFmt: function (v) { return (v > 0 ? "+" : "") + v.toFixed(2); }, label: "Front-running meter"
    });
    $("fr-label").textContent = F.label || "—";
    var fh = F.flow_hits || {};
    $("fr-text").textContent = "Score from " + (F.source || "—") + " (n = " + (F.n || 0) + "). Above +0.2 the leaders' changes tend to come before price moves; below −0.2 they follow them." +
      (fh.n ? " Flow followed by a same-direction move " + pct(fh.hit_rate, 0) + " of the time (n = " + fh.n + ", " + fh.ahead_steps + " steps ahead)." : "");
    $("ll-text").textContent = [L.live && ("Live: " + L.live.text), L.reconstructed && ("Reconstructed: " + L.reconstructed.text)].filter(Boolean).join(" ");
  }

  // ---------------------------------------------------------------- x sentiment
  function xSentiment(d, I) {
    var X = I.x_sentiment || {};
    if (X.status === "CONNECTED" && X.data) {
      $("x-status").textContent = "Net sentiment " + (X.data.score > 0 ? "+" : "") + X.data.score.toFixed(2) + " from " + X.data.n_posts + " posts" +
        (X.data.window_hours ? " over " + X.data.window_hours + "h" : "") + ". " + (X.data.method || "");
    }
  }

  function renderAll() {
    var d = state.data;
    if (!d) return;
    var I = d.intel;
    if (!I) {
      $("board").innerHTML = "<tbody><tr><th scope='row'>Market intelligence</th><td class='val'>—</td><td class='why'>This snapshot predates the intelligence layer.</td></tr></tbody>";
      history(d, state.history);
      return;
    }
    var steps = [readout, function () { history(d, state.history); }, priceAction, regimeFG, liqMap,
      function () { fundingOI(d, I, state.history); }, flips, risk, integrity, bayes, contrarian, backtest, leadLag, xSentiment];
    steps.forEach(function (fn) {
      try { fn(d, I); } catch (err) { if (window.console) console.warn("panel failed", err); }
    });
  }

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(renderAll, 150);
  });

  window.renderIntel = function (data, hist) {
    state.data = data;
    state.history = hist && hist.length ? hist : (data.history || []);
    renderAll();
  };
})();
