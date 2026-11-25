"""The published 30-day backtest: data consistency, formulas in the note, site wiring, and sweep isolation."""
from __future__ import annotations

import csv
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "research" / "backtest-30d"
SITE = ROOT / "site"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, RES / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rows():
    return list(csv.DictReader((RES / "data" / "daily_backtest.csv").open()))


def test_daily_csv_is_thirty_consistent_days():
    rows = _rows()
    assert [int(r["day"]) for r in rows] == list(range(1, 31))
    eq = 1.0
    for r in rows:
        eq *= 1 + float(r["net_pnl_pct"]) / 100
        assert abs((eq - 1) * 100 - float(r["cumulative_pnl_pct"])) < 0.06
        assert r["signal"] in {"LONG", "SHORT", "NEUTRAL"}
        assert 0 <= float(r["p_long"]) <= 1
        net = float(r["gross_pnl_pct"]) + float(r["fees_pct"]) + float(r["funding_pct"])
        assert abs(net - float(r["net_pnl_pct"])) < 0.01
    res = json.loads((RES / "data" / "results.json").read_text())
    assert abs(res["daily"]["total_return"] * 100 - float(rows[-1]["cumulative_pnl_pct"])) < 0.06


def test_signal_never_left_short_so_strategy_equals_always_short():
    res = json.loads((RES / "data" / "results.json").read_text())
    assert res["p_stats"]["hours_not_short"] == 0
    assert abs(res["daily"]["total_return"] - res["short_daily"]["total_return"]) < 1e-12
    assert res["daily"]["trades"] == 1


def test_analysis_reproduces_committed_result():
    A = _load("analyze")
    mk, wallets, opn, fund, end, start = A.load()
    P = {t: A.cohort_p(wallets, opn, t) for t in range(start, end, A.D)}
    rows, _ = A.run(P, opn, fund, start, end, 24)
    res = json.loads((RES / "data" / "results.json").read_text())
    assert abs(A.stats(rows, 24)["total_return"] - res["daily"]["total_return"]) < 1e-9
    assert abs(A.stats(A.fixed(-1, opn, fund, start, end, 24), 24)["total_return"] - res["short_daily"]["total_return"]) < 1e-9


def test_every_formula_is_in_the_research_note_in_github_safe_form():
    B = _load("build_docs")
    note = (RES / "README.md").read_text()
    for key, (tex, _alt) in B.F.items():
        assert f"$$\n{tex}\n$$" in note, key
    for bad in (r"\operatorname", r"\#", r"\eqref", r"\label"):
        assert bad not in note
    assert note.count("$$") % 2 == 0
    flat = re.sub(r"\$\$.*?\$\$", "", note, flags=re.S)
    assert flat.count("$") % 2 == 0
    assert len(re.findall(r"^\| \d+ \| 2026-", note, flags=re.M)) == 30


def test_note_numbers_match_results():
    res = json.loads((RES / "data" / "results.json").read_text())
    note = (RES / "README.md").read_text()
    main = (ROOT / "README.md").read_text()
    total = f"{res['daily']['total_return'] * 100:+.1f}%"
    hold = f"{res['hold_daily']['total_return'] * 100:+.1f}%".replace("-", "\u2212")
    for text in (note, main):
        assert total in text and hold in text


def test_site_has_tabs_and_backtest_data():
    html = (SITE / "index.html").read_text()
    for needle in ('role="tablist"', 'id="tab-signal"', 'id="tab-backtest"', 'id="panel-signal"', 'id="panel-backtest"',
                   "BACKTEST:START", "BACKTEST:END", "js/tabs.js", "js/backtest.js"):
        assert needle in html, needle
    assert html.count('class="bt-eq"') == 14
    assert len(re.findall(r"<tr><td>\d+</td><td class=\"l\">2026-", html)) == 30
    for name in ("daily_backtest.csv", "results.json", "extra.json", "hourly_signal.csv", "backtest.json",
                 "equity_curve_30d.png", "daily_table_30d.png"):
        assert (SITE / "backtest" / name).exists(), name
    for name in ("daily_backtest.csv", "results.json"):
        assert (SITE / "backtest" / name).read_bytes() == (RES / "data" / name).read_bytes()
    chart = json.loads((SITE / "backtest" / "backtest.json").read_text())
    assert len(chart["t"]) == len(chart["follow"]) == len(chart["short"]) == len(chart["hold"]) == 31


def test_sweep_cannot_overwrite_or_drop_the_backtest_files():
    wf = (ROOT / ".github" / "workflows" / "sweep.yml").read_text()
    adds = [ln for ln in wf.splitlines() if "git add" in ln]
    assert adds and all("site/backtest" not in ln and " site " not in ln + " " and "-A" not in ln and " ." not in ln for ln in adds)
    from app import config
    assert config.SITE_DATA_DIR == SITE / "data"  # the sweep writes only site/data
    src = "".join(p.read_text() for p in (ROOT / "app").glob("*.py"))
    assert "rmtree" not in src


def test_no_forbidden_words_or_secrets_in_published_files():
    banned = re.compile(r"\b(BITS|Pilani|university|college|campus)\b", re.I)
    secret = re.compile(r"(ghp_|gho_|github_pat_|BEGIN (RSA|OPENSSH|PRIVATE)|api[_-]?key\s*=|Authorization:)", re.I)
    files = [RES / "README.md", SITE / "index.html", SITE / "styles.css", *(RES / "scripts").glob("*"), *SITE.joinpath("js").glob("*.js")]
    for f in files:
        if f.is_file():
            t = f.read_text()
            assert not banned.search(t), f
            assert not secret.search(t), f
