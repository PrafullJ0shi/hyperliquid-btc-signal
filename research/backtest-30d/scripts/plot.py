"""Render the two figures. Needs matplotlib. IBM Plex is used when installed, else the default font.

    python research/backtest-30d/scripts/plot.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as md  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402

BASE = Path(__file__).resolve().parents[1]
DATA, FIG = BASE / "data", BASE / "figures"
FIG.mkdir(exist_ok=True)

for f in fm.findSystemFonts():
    if "IBMPlexMono" in f or "IBMPlexSans-Var" in f:
        fm.fontManager.addfont(f)
have = {f.name for f in fm.fontManager.ttflist}
SANS = "IBM Plex Sans" if "IBM Plex Sans" in have else "DejaVu Sans"
MONO = "IBM Plex Mono" if "IBM Plex Mono" in have else "DejaVu Sans Mono"
PAPER, INK, MUTED, HAIR, RED, GREY = "#EFECE6", "#141414", "#3F3F3A", "#B7B3A9", "#8C1D12", "#8A867D"
plt.rcParams.update({"font.family": SANS, "text.color": INK, "axes.edgecolor": INK, "axes.labelcolor": INK, "xtick.color": INK,
                     "ytick.color": INK, "figure.facecolor": PAPER, "axes.facecolor": PAPER, "savefig.facecolor": PAPER})
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
R = json.loads((DATA / "results.json").read_text())
S = json.loads((DATA / "series.json").read_text())
rows = list(csv.DictReader((DATA / "daily_backtest.csv").open()))
hourly = list(csv.DictReader((DATA / "hourly_signal.csv").open()))


def d(ms):
    return dt.datetime.fromtimestamp(ms / 1000, IST)


# ------------------------------------------------------------------ Fig. A: equity curve
fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(11, 9), gridspec_kw={"height_ratios": [3, 1.4, 1.1]}, sharex=True)
dr, dc = S["daily"]
x = [d(t) for t, _ in dc]
a1.axhline(0, color=INK, lw=0.6)
a1.plot([d(t) for t, _ in S["hourly"][1]], [(e - 1) * 100 for _, e in S["hourly"][1]], color=GREY, lw=0.8, label="Follow the signal, hourly rebalance")
a1.plot(x, [(e - 1) * 100 for e in S["hold_curve"]], color=INK, lw=1.2, ls="--", label="Buy and hold BTC")
a1.plot(x, [(e - 1) * 100 for e in S["short_curve"]], color=INK, lw=1.4, ls=":", label="Always short")
a1.plot(x, [(e - 1) * 100 for _, e in dc], color=RED, lw=2.0, label="Follow the signal, daily rebalance (primary)")
a1.set_ylabel("Cumulative P&L, % (after fees and funding)")
a1.legend(frameon=False, loc="upper left", fontsize=8.5)
a1.text(0.02, 0.60, f"The signal read SHORT in all {R['p_stats']['hours']} hourly reads (P(long) never above {R['p_stats']['p_max']:.2f}),\n"
        "so the daily line is the always-short line.", transform=a1.transAxes, fontsize=9, color=RED)
a1.set_title("Following the Hyperliquid BTC signal for 30 days (reconstructed)", loc="left", fontsize=13, fontfamily=MONO, fontweight="semibold")
a1.grid(axis="y", color=HAIR, lw=0.5)
ht = [dt.datetime.strptime(h["time_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc).astimezone(IST) for h in hourly]
a2.plot(ht, [float(h["p_long"]) for h in hourly], color=RED, lw=1.3)
for lv in (0.40, 0.60):
    a2.axhline(lv, color=INK, lw=0.7, ls="--")
a2.text(ht[-1], 0.405, " SHORT at or below 0.40", fontsize=8, va="bottom", ha="right", color=MUTED)
a2.text(ht[-1], 0.605, " LONG at or above 0.60", fontsize=8, va="bottom", ha="right", color=MUTED)
a2.set_ylim(0, 0.8)
a2.set_ylabel("P(long)")
a2.grid(axis="y", color=HAIR, lw=0.5)
a3.plot(x, [R["btc_start"]] + [float(r["btc_next_day_price"]) for r in rows], color=INK, lw=1.2, drawstyle="steps-post")
a3.set_ylabel("BTC, USD")
for ax in (a1, a2, a3):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
a3.xaxis.set_major_formatter(md.DateFormatter("%d %b"))
a3.xaxis.set_major_locator(md.DayLocator(interval=3))
fig.text(0.01, 0.005, "Signal read at 05:30 IST (00:00 UTC). Taker fee 0.045% per side; hourly funding from fundingHistory. "
         f"Cohort rebuilt from userFillsByTime of {R['n_wallets']} wallets (survivorship bias: today's leaders).", fontsize=7.5, color=MUTED)
fig.tight_layout(rect=(0, 0.02, 1, 1))
fig.savefig(FIG / "equity_curve_30d.png", dpi=170)
plt.close(fig)

# ------------------------------------------------------------------ Fig. B: day-by-day table
n = len(rows)
fig, ax = plt.subplots(figsize=(13.5, 0.34 * (n + 4)))
ax.axis("off")
spec = [("Day", 0.005, "left"), ("Date (IST)", 0.045, "left"), ("Signal", 0.12, "left"), ("P(long)", 0.235, "right"), ("Action", 0.26, "left"),
        ("BTC entry", 0.455, "right"), ("BTC next day", 0.54, "right"), ("BTC move", 0.62, "right"), ("Fees", 0.69, "right"),
        ("Funding", 0.76, "right"), ("Day P&L", 0.845, "right"), ("Cumulative", 0.94, "right")]
N = n + 1


def y(i):
    return 1 - (i + 0.5) / (N + 1.5)


for c, xx, h in spec:
    ax.text(xx, y(0), c, ha=h, va="center", fontsize=8.5, fontweight="semibold", family=MONO, transform=ax.transAxes)
ax.plot([0, 0.95], [y(0) - 0.5 / (N + 1.5)] * 2, color=INK, lw=0.9, transform=ax.transAxes)


def fmt(v, nd=2):
    return f"{float(v):+.{nd}f}%"


for i, r in enumerate(rows, 1):
    yy = y(i)
    net, cum, sig = float(r["net_pnl_pct"]), float(r["cumulative_pnl_pct"]), r["signal"]
    vals = [r["day"], r["date_ist"][5:], sig, f"{float(r['p_long']):.3f}", r["action"], f"{float(r['btc_entry_price']):,.0f}",
            f"{float(r['btc_next_day_price']):,.0f}", fmt(r["btc_move_pct"]), (f"{float(r['fees_pct']):.3f}%" if float(r["fees_pct"]) else "-"),
            fmt(r["funding_pct"], 3), fmt(net), fmt(cum)]
    for j, (v, (_, xx, h)) in enumerate(zip(vals, spec)):
        col = RED if (j == 10 and net < 0) or (j == 11 and cum < 0) or (j == 2 and sig == "SHORT") else INK
        ax.text(xx, yy, v, ha=h, va="center", fontsize=8.2, family=MONO, color=col, transform=ax.transAxes,
                fontweight="semibold" if j in (2, 11) else "normal")
    if i % 5 == 0:
        ax.plot([0, 0.95], [yy - 0.5 / (N + 1.5)] * 2, color=HAIR, lw=0.5, transform=ax.transAxes)
t = R["daily"]
ax.text(0.005, y(N + 0.8), f"Day 30 cumulative: {t['total_return'] * 100:+.1f}% after fees and funding.   Buy and hold, same window: "
        f"{R['hold_daily']['total_return'] * 100:+.1f}%.   Always short: {R['short_daily']['total_return'] * 100:+.1f}%.   Red = loss or SHORT.",
        fontsize=8.5, transform=ax.transAxes)
fig.suptitle("Day-by-day: signal read at 05:30 IST, one unit of BTC perp, rebalanced daily", x=0.01, ha="left", fontsize=12,
             fontfamily=MONO, fontweight="semibold", y=0.995)
fig.savefig(FIG / "daily_table_30d.png", dpi=160, bbox_inches="tight")
plt.close(fig)
print("wrote", FIG)
