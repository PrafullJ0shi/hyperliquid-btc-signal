/* Small hand-built SVG chart helpers. No dependencies. */
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var C = { ink: "#141414", muted: "#3F3F3A", hair: "#B7B3A9", accent: "#8C1D12", paper: "#EFECE6", grey: "#8A867D" };
  var MONO = "IBM Plex Mono, ui-monospace, monospace";

  function el(tag, attrs, parent) {
    var n = document.createElementNS(NS, tag);
    if (attrs) for (var k in attrs) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }

  function surface(container, label) {
    while (container.firstChild) container.removeChild(container.firstChild);
    var w = Math.max(200, Math.floor(container.clientWidth || 600));
    var h = Math.floor(container.clientHeight || parseInt(container.style.height, 10) || 160);
    var svg = el("svg", { width: w, height: h, viewBox: "0 0 " + w + " " + h, role: "img", "aria-label": label || "" }, container);
    return { svg: svg, w: w, h: h };
  }

  function text(svg, x, y, s, o) {
    o = o || {};
    var t = el("text", {
      x: x, y: y, "font-size": o.size || 10, "font-family": o.font || MONO,
      fill: o.fill || C.muted, "text-anchor": o.anchor || "start", "dominant-baseline": o.base || "auto"
    }, svg);
    t.textContent = s;
    return t;
  }

  function line(svg, x1, y1, x2, y2, stroke, width, dash) {
    return el("line", { x1: x1, y1: y1, x2: x2, y2: y2, stroke: stroke || C.ink, "stroke-width": width || 1, "stroke-dasharray": dash || null, "shape-rendering": "crispEdges" }, svg);
  }

  function path(svg, pts, stroke, width, dash) {
    var d = "", pen = false;
    pts.forEach(function (p) {
      if (p == null || p[1] == null || isNaN(p[1])) { pen = false; return; }
      d += (pen ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1);
      pen = true;
    });
    if (!d) return null;
    return el("path", { d: d, fill: "none", stroke: stroke || C.ink, "stroke-width": width || 1, "stroke-dasharray": dash || null, "stroke-linejoin": "round" }, svg);
  }

  function scale(d0, d1, r0, r1) {
    var k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
    return function (v) { return r0 + (v - d0) * k; };
  }

  function extent(arr) {
    var lo = Infinity, hi = -Infinity;
    arr.forEach(function (v) { if (v != null && !isNaN(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } });
    if (lo === Infinity) return [0, 1];
    if (lo === hi) { lo -= 1; hi += 1; }
    return [lo, hi];
  }

  function niceTicks(lo, hi, n) {
    var span = hi - lo, step = Math.pow(10, Math.floor(Math.log10(span / n)));
    var err = (n * step) / span;
    if (err <= 0.15) step *= 10; else if (err <= 0.35) step *= 5; else if (err <= 0.75) step *= 2;
    var out = [];
    for (var v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }

  var IST_FMT = typeof Intl !== "undefined" ? new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }) : null;
  var IST_DAY = typeof Intl !== "undefined" ? new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short" }) : null;
  function fmtTime(ms, dayOnly) {
    var d = new Date(ms);
    if (!IST_FMT) return d.toISOString().slice(5, 16);
    return (dayOnly ? IST_DAY : IST_FMT).format(d);
  }

  function timeAxis(svg, x, t0, t1, y, n, dayOnly) {
    var span = t1 - t0;
    for (var i = 0; i <= n; i++) {
      var t = t0 + (span * i) / n;
      var xx = x(t);
      line(svg, xx, y, xx, y + 3, C.ink, 1);
      text(svg, xx, y + 13, fmtTime(t, dayOnly), { anchor: i === 0 ? "start" : (i === n ? "end" : "middle"), size: 9 });
    }
  }

  function fmtK(v) {
    var a = Math.abs(v);
    if (a >= 1e9) return (v / 1e9).toFixed(2) + "b";
    if (a >= 1e6) return (v / 1e6).toFixed(a >= 1e7 ? 0 : 1) + "m";
    if (a >= 1e3) return (v / 1e3).toFixed(a >= 1e4 ? 0 : 1) + "k";
    return String(Math.round(v));
  }

  function empty(container, msg) {
    var s = surface(container, msg);
    line(s.svg, 0, s.h / 2, s.w, s.h / 2, C.hair, 1, "2 3");
    text(s.svg, 4, s.h / 2 - 6, msg, { size: 11 });
    return s;
  }

  // Candlestick chart with optional EMA overlays. candles: [[t,o,h,l,c],...]
  function candles(container, cs, emas, opts) {
    opts = opts || {};
    if (!cs || cs.length < 2) return empty(container, "No candles in this snapshot.");
    var s = surface(container, opts.label);
    var padL = 4, padR = opts.compact ? 44 : 52, padT = 6, padB = opts.compact ? 16 : 20;
    var lows = cs.map(function (c) { return c[3]; }), highs = cs.map(function (c) { return c[2]; });
    var all = lows.concat(highs);
    if (emas && !opts.emaOutOfScale) Object.keys(emas).forEach(function (k) { (emas[k] || []).forEach(function (v) { if (v != null) all.push(v); }); });
    var ex = extent(all);
    var pad = (ex[1] - ex[0]) * 0.04;
    var y = scale(ex[0] - pad, ex[1] + pad, s.h - padB, padT);
    var bw = (s.w - padL - padR) / cs.length;
    var x = function (i) { return padL + bw * (i + 0.5); };
    niceTicks(ex[0], ex[1], opts.compact ? 3 : 5).forEach(function (v) {
      line(s.svg, padL, y(v), s.w - padR, y(v), C.hair, 0.6, "1 3");
      text(s.svg, s.w - padR + 4, y(v) + 3, fmtK(v), { size: 9 });
    });
    var body = Math.max(1, bw * 0.62);
    cs.forEach(function (c, i) {
      var up = c[4] >= c[1];
      line(s.svg, x(i), y(c[2]), x(i), y(c[3]), C.ink, 0.8);
      var top = y(Math.max(c[1], c[4])), bot = y(Math.min(c[1], c[4]));
      el("rect", { x: x(i) - body / 2, y: top, width: body, height: Math.max(0.8, bot - top), fill: up ? C.paper : C.ink, stroke: C.ink, "stroke-width": 0.7 }, s.svg);
    });
    if (emas) {
      var style = { e20: [C.ink, 0.9, null], e50: [C.ink, 1, "4 3"], e200: [C.grey, 2, null] };
      Object.keys(style).forEach(function (k) {
        var arr = emas[k] || [];
        var off = cs.length - arr.length;
        path(s.svg, arr.map(function (v, i) { return v == null ? null : [x(i + off), y(v)]; }), style[k][0], style[k][1], style[k][2]);
      });
    }
    if (opts.mark) {
      var ym = y(opts.mark);
      line(s.svg, s.w - padR, ym, s.w - padR + 6, ym, C.accent, 2);
    }
    timeAxis(s.svg, function (t) { return padL + (t - cs[0][0]) / (cs[cs.length - 1][0] - cs[0][0]) * (s.w - padL - padR); }, cs[0][0], cs[cs.length - 1][0], s.h - padB, (opts.compact || s.w < 560) ? 2 : 4, !!opts.daily);
    line(s.svg, padL, s.h - padB, s.w - padR, s.h - padB, C.ink, 1);
    return s;
  }

  // Two-scale time series. series: [{pts:[[t,v]], axis:"left"|"right", stroke, width, dash}]
  function timeseries(container, series, opts) {
    opts = opts || {};
    var pts = [];
    series.forEach(function (sr) { pts = pts.concat(sr.pts.filter(function (p) { return p[1] != null; })); });
    if (pts.length < 2) return empty(container, opts.emptyMsg || "Not enough stored points yet.");
    var s = surface(container, opts.label);
    var padL = opts.leftLabels === false ? 4 : 34, padR = opts.rightLabels ? 46 : 8, padT = 6, padB = 20;
    var ts = pts.map(function (p) { return p[0]; });
    var t0 = Math.min.apply(null, ts), t1 = Math.max.apply(null, ts);
    if (t1 === t0) t1 = t0 + 1;
    var x = scale(t0, t1, padL, s.w - padR);
    var left = opts.leftDomain || extent([].concat.apply([], series.filter(function (r) { return r.axis !== "right"; }).map(function (r) { return r.pts.map(function (p) { return p[1]; }); })));
    var right = extent([].concat.apply([], series.filter(function (r) { return r.axis === "right"; }).map(function (r) { return r.pts.map(function (p) { return p[1]; }); })));
    var yl = scale(left[0], left[1], s.h - padB, padT);
    var yr = scale(right[0], right[1], s.h - padB, padT);
    (opts.leftRefs || []).forEach(function (r) { line(s.svg, padL, yl(r[0]), s.w - padR, yl(r[0]), r[1] || C.hair, 1, r[2]); });
    if (opts.leftLabels !== false) {
      (opts.leftTicks || niceTicks(left[0], left[1], 4)).forEach(function (v) {
        text(s.svg, padL - 4, yl(v) + 3, opts.leftFmt ? opts.leftFmt(v) : String(v), { anchor: "end", size: 9 });
      });
    }
    if (opts.rightLabels) {
      niceTicks(right[0], right[1], 3).forEach(function (v) { text(s.svg, s.w - padR + 4, yr(v) + 3, opts.rightFmt ? opts.rightFmt(v) : fmtK(v), { size: 9, fill: C.grey }); });
    }
    series.forEach(function (sr) {
      var yy = sr.axis === "right" ? yr : yl;
      var gap = opts.gapMs || Infinity, prevT = null;
      var arr = [];
      sr.pts.forEach(function (p) {
        if (prevT != null && p[0] - prevT > gap) arr.push(null);
        arr.push(p[1] == null ? null : [x(p[0]), yy(p[1])]);
        prevT = p[0];
      });
      path(s.svg, arr, sr.stroke, sr.width, sr.dash);
      if (sr.dots) arr.forEach(function (q) { if (q) el("circle", { cx: q[0], cy: q[1], r: 1.6, fill: sr.stroke }, s.svg); });
    });
    line(s.svg, padL, s.h - padB, s.w - padR, s.h - padB, C.ink, 1);
    timeAxis(s.svg, x, t0, t1, s.h - padB, s.w < 500 ? 2 : 4, opts.dayOnly);
    return s;
  }

  // Horizontal 0..1 (or lo..hi) scale with a needle.
  function meter(container, value, opts) {
    opts = opts || {};
    var s = surface(container, opts.label);
    var lo = opts.lo != null ? opts.lo : 0, hi = opts.hi != null ? opts.hi : 100;
    var padX = 10, y0 = 26;
    var x = scale(lo, hi, padX, s.w - padX);
    line(s.svg, padX, y0, s.w - padX, y0, C.ink, 1);
    (opts.bands || []).forEach(function (b) {
      line(s.svg, x(b[0]), y0 - 5, x(b[0]), y0 + 5, C.ink, 1);
    });
    (opts.ticks || []).forEach(function (t) {
      line(s.svg, x(t[0]), y0, x(t[0]), y0 + 4, C.ink, 1);
      text(s.svg, x(t[0]), y0 + 16, t[1], { anchor: t[0] === lo ? "start" : (t[0] === hi ? "end" : "middle"), size: 9, font: "IBM Plex Sans, sans-serif" });
    });
    if (value != null && !isNaN(value)) {
      var xv = x(Math.max(lo, Math.min(hi, value)));
      line(s.svg, xv, y0 - 14, xv, y0 + 6, C.accent, 2.5);
      text(s.svg, xv, y0 - 17, opts.valueFmt ? opts.valueFmt(value) : String(value), { anchor: xv < 40 ? "start" : (xv > s.w - 40 ? "end" : "middle"), size: 11, fill: C.accent });
    }
    return s;
  }

  window.HLCharts = { C: C, el: el, surface: surface, text: text, line: line, path: path, scale: scale, extent: extent, niceTicks: niceTicks, fmtTime: fmtTime, fmtK: fmtK, empty: empty, candles: candles, timeseries: timeseries, meter: meter, timeAxis: timeAxis };
})();
