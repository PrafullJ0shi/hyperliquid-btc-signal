/* Backtest tab: equity curve and P(long) strip, drawn from backtest/backtest.json. */
(function () {
  "use strict";
  var DATA_URL = "backtest/backtest.json";
  var data = null, loading = null;

  function load() {
    if (!loading) {
      loading = fetch(DATA_URL).then(function (r) {
        if (!r.ok) throw new Error("backtest.json HTTP " + r.status);
        return r.json();
      }).then(function (d) { data = d; return d; });
    }
    return loading;
  }

  function pctFmt(v) { return (v > 0 ? "+" : v < 0 ? "\u2212" : "") + Math.abs(v) + "%"; }

  function draw() {
    var H = window.HLCharts, C = H && H.C;
    var eq = document.getElementById("bt-chart-equity"), pe = document.getElementById("bt-chart-p");
    if (!H || !data || !eq || !pe || !eq.clientWidth) return;
    function pts(t, v) { return t.map(function (x, i) { return [x, v[i] * 100]; }); }
    H.timeseries(eq, [
      { pts: pts(data.hourly_t, data.hourly), stroke: C.grey, width: 1 },
      { pts: pts(data.t, data.hold), stroke: C.ink, width: 1.2, dash: "5 3" },
      { pts: pts(data.t, data.short), stroke: C.ink, width: 1.4, dash: "1 3" },
      { pts: pts(data.t, data.follow), stroke: C.accent, width: 2 }
    ], { label: "Cumulative P&L of each rule, percent", leftFmt: pctFmt, leftRefs: [[0, C.ink]], dayOnly: true });
    var s = H.timeseries(pe, [{ pts: data.p, stroke: C.accent, width: 1.3 }], {
      label: "Hourly P(long) against the 0.40 and 0.60 thresholds", leftDomain: [0, 0.8], leftTicks: [0, 0.2, 0.4, 0.6, 0.8],
      leftFmt: function (v) { return v.toFixed(1); }, leftRefs: [[0.4, C.ink, "4 3"], [0.6, C.ink, "4 3"]], dayOnly: true
    });
    if (s && s.svg) {
      var y = H.scale(0, 0.8, s.h - 20, 6);
      H.text(s.svg, s.w - 8, y(0.6) - 3, "LONG at or above 0.60", { anchor: "end", size: 9 });
      H.text(s.svg, s.w - 8, y(0.4) - 3, "SHORT at or below 0.40", { anchor: "end", size: 9 });
    }
  }

  window.renderBacktest = function () {
    load().then(draw).catch(function (err) {
      var H = window.HLCharts, a = document.getElementById("bt-chart-equity");
      if (H && a) H.empty(a, "Chart data unavailable (" + err.message + "). Table B2 has the same numbers.");
    });
  };

  var timer = null;
  window.addEventListener("resize", function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      var panel = document.getElementById("panel-backtest");
      if (panel && !panel.hidden) draw();
    }, 150);
  });
})();
