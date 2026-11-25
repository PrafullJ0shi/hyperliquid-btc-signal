/* Hash-routed tabs: #signal (default), #flows and #backtest. An anchor inside a panel opens that panel. */
(function () {
  "use strict";
  var NAMES = ["signal", "flows", "backtest"];
  var TITLES = {
    signal: null,
    flows: "Flows, whales and liquidations, Hyperliquid BTC",
    backtest: "Backtest: 30 days of following the signal, Hyperliquid BTC consensus"
  };
  var tabs = {}, panels = {}, signalTitle = null, current = null;

  function $(id) { return document.getElementById(id); }

  function routeFromHash() {
    var h = decodeURIComponent((location.hash || "").replace(/^#/, ""));
    if (!h || h === "signal") return { tab: "signal", anchor: null };
    if (h === "backtest" || h === "flows") return { tab: h, anchor: null };
    var el = $(h);
    if (el && panels.backtest.contains(el)) return { tab: "backtest", anchor: el };
    if (el && panels.flows && panels.flows.contains(el)) return { tab: "flows", anchor: el };
    return { tab: "signal", anchor: el && panels.signal.contains(el) ? el : null };
  }

  function show(name, anchor, fromUser) {
    var changed = name !== current;
    NAMES.forEach(function (n) {
      var on = n === name;
      panels[n].hidden = !on;
      tabs[n].setAttribute("aria-selected", on ? "true" : "false");
      tabs[n].tabIndex = on ? 0 : -1;
    });
    current = name;
    if (name === "backtest") {
      document.title = TITLES.backtest;
      if (typeof window.renderBacktest === "function") window.renderBacktest();
    } else if (name === "flows") {
      document.title = TITLES.flows;
      // Charts need a visible container to measure their width.
      if (changed && typeof window.renderFlows === "function") window.renderFlows();
    } else {
      if (signalTitle) document.title = signalTitle;
      // Charts drawn while this panel was hidden have no width: redraw them.
      if (changed) window.dispatchEvent(new Event("resize"));
    }
    if (anchor) {
      anchor.scrollIntoView();
    } else if (changed || fromUser) {
      window.scrollTo(0, 0);
    }
  }

  function apply(fromUser) {
    var r = routeFromHash();
    show(r.tab, r.anchor, fromUser);
  }

  function select(name) {
    var want = "#" + name;
    if (location.hash === want || (name === "signal" && !location.hash)) { show(name, null, true); return; }
    location.hash = want;
  }

  function boot() {
    NAMES.forEach(function (n) { tabs[n] = $("tab-" + n); panels[n] = $("panel-" + n); });
    if (!tabs.signal || !tabs.backtest) return;
    if (!tabs.flows || !panels.flows) NAMES = NAMES.filter(function (n) { return n !== "flows"; });
    signalTitle = document.title;
    NAMES.forEach(function (n, i) {
      tabs[n].addEventListener("click", function () { select(n); });
      tabs[n].addEventListener("keydown", function (e) {
        var j = null;
        if (e.key === "ArrowRight") j = (i + 1) % NAMES.length;
        else if (e.key === "ArrowLeft") j = (i + NAMES.length - 1) % NAMES.length;
        else if (e.key === "Home") j = 0;
        else if (e.key === "End") j = NAMES.length - 1;
        if (j === null) return;
        e.preventDefault();
        tabs[NAMES[j]].focus();
        select(NAMES[j]);
      });
    });
    window.addEventListener("hashchange", function () { apply(false); });
    apply(false);
    // app.js sets document.title when data arrives; keep the Backtest title on that tab.
    var t = document.querySelector("title");
    if (t && window.MutationObserver) {
      new MutationObserver(function () {
        var cur = document.title;
        if (cur !== TITLES.backtest && cur !== TITLES.flows) {
          signalTitle = cur;
          if (current === "backtest" || current === "flows") document.title = TITLES[current];
        }
      }).observe(t, { childList: true });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
