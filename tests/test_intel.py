import math

from app import indicators as ind
from app import intel as I

HOUR = 3_600_000


def test_ema_seed_and_recursion():
    vals = [1, 2, 3, 4, 5, 6]
    e = ind.ema(vals, 3)
    assert e[:2] == [None, None]
    assert e[2] == 2.0
    alpha = 0.5
    assert abs(e[3] - (alpha * 4 + (1 - alpha) * 2.0)) < 1e-12
    assert ind.ema([1, 2], 3) == [None, None]


def test_efficiency_ratio_extremes():
    assert ind.efficiency_ratio([1, 2, 3, 4, 5]) == 1.0
    assert ind.efficiency_ratio([1, 2, 1, 2, 1]) == 0.0


def test_realized_vol_constant_growth_is_zero():
    prices = [100 * (1.01 ** i) for i in range(30)]
    assert ind.realized_vol(prices, 24 * 365) < 1e-9


def test_cross_correlation_detects_lead():
    x = [math.sin(i / 3.0) for i in range(120)]
    y = [None, None] + x[:-2]  # y repeats x two steps later: x leads by +2
    ccf = ind.cross_correlation(x, y, 4)
    best = max((c for c in ccf if c["r"] is not None), key=lambda c: c["r"])
    assert best["lag"] == 2
    assert ind.lead_score(ccf) > 0


def test_regime_classification():
    assert ind.classify_regime(0.9, 0.1, -0.05, -1)["label"] == "HIGH-VOL"
    assert ind.classify_regime(0.9, 0.1, -0.05, -1)["sub"] == "panic"
    assert ind.classify_regime(0.5, 0.4, 0.01, 1)["label"] == "TRENDING"
    assert ind.classify_regime(0.5, 0.1, 0.01, 1)["label"] == "RANGING"
    assert ind.classify_regime(None, 0.1, 0.0, 0)["label"] == "UNKNOWN"


def test_liq_distance_and_grades():
    assert abs(I.liq_distance(1, 100.0, 90.0) - 0.10) < 1e-12
    assert abs(I.liq_distance(-1, 100.0, 120.0) - 0.20) < 1e-12
    assert I.liq_distance(1, 100.0, None) is None
    assert I.grade_from_z(12) == "A"
    assert I.grade_from_z(3) == "D"
    assert I.grade_from_z(1) == "F"
    assert I.grade_from_vol(0.4) == "F"
    assert I.worse("A", "D") == "D"


def test_cohort_risk_flags_squeeze():
    obs = []
    for i in range(10):
        obs.append({"address": f"s{i}", "btc_szi": -1.0, "btc_notional": 1e6, "equity": 1e5,
                    "total_ntl": 1e6, "liquidation_px": 102.0, "month_pnl": 1e5})
    r = I.cohort_risk(obs, 100.0, 0.02, 0.05)
    assert r["available"]
    assert r["short"]["df_share"] == 1.0
    assert r["squeeze"]["level"] == "HIGH"
    assert r["squeeze"]["side_at_risk"] == "SHORT"


def test_liquidation_map_bins():
    obs = [
        {"btc_szi": -1, "btc_notional": 100.0, "liquidation_px": 104.5},
        {"btc_szi": 1, "btc_notional": 50.0, "liquidation_px": 97.2},
        {"btc_szi": 1, "btc_notional": 10.0, "liquidation_px": None},
    ]
    m = I.liquidation_map(obs, 100.0)
    assert m["shorts_liq_within_5pct_up"] == 100.0
    assert m["longs_liq_within_5pct_down"] == 50.0
    assert m["no_liq_px"]["long_ntl"] == 10.0
    assert m["peak_above"]["ntl"] == 100.0


def test_classify_change():
    assert I.classify_change(0, 1) == "OPEN"
    assert I.classify_change(1, 0) == "CLOSE"
    assert I.classify_change(1, -1) == "FLIP"
    assert I.classify_change(1, 2) == "ADD"
    assert I.classify_change(-2, -1) == "CUT"
    assert I.classify_change(0, 0) is None


def test_position_changes_flow_and_flips():
    prev = {"ts_utc": "x", "mark": 100.0, "positions": {"a": -10.0, "b": 5.0, "gone": 1.0}}
    obs = [
        {"address": "a", "btc_szi": 10.0, "equity": 1e6, "month_pnl": 1e6},
        {"address": "b", "btc_szi": 5.0, "equity": 1e6, "month_pnl": 1e6},
        {"address": "new", "btc_szi": 3.0, "equity": 1e6, "month_pnl": 1e6},
    ]
    c = I.position_changes(obs, prev, 100.0)
    assert c["counts"]["FLIP"] == 1 and c["flips_to_long"] == 1
    assert c["net_notional_flow"] == 2000.0
    assert c["net_weight_flow"] > 0
    assert c["cohort_churn_in"] == 1 and c["cohort_churn_out"] == 1
    assert I.position_changes(obs, None, 100.0)["available"] is False


def test_flip_status_levels():
    stable = I.flip_status({"available": True, "net_weight_flow": 0.0, "net_flips": 0,
                            "flips_to_long": 0, "flips_to_short": 0}, 0.0, 0.01, 0.02, 200)
    assert stable["status"] == "STABLE"
    turning = I.flip_status({"available": True, "net_weight_flow": 0.2, "net_flips": 12,
                             "flips_to_long": 12, "flips_to_short": 0}, 0.1, 0.15, 0.2, 200)
    assert turning["status"] == "TURNING LONG"


def test_concentration_and_leave_out():
    c = I.concentration([1, 1, 1, 1])
    assert abs(c["n_eff"] - 4) < 1e-12
    assert abs(c["hhi"] - 0.25) < 1e-12
    signed = [(1, 100.0), (-1, 1.0), (-1, 1.0), (-1, 1.0)]
    assert I.p_without_top(signed, 1) == 0.0


def test_bayes_replay_converges_and_forgets():
    pts = [{"_ms": i * 30 * 60_000, "p_long": 0.1, "n_eff": 50} for i in range(200)]
    rep = I.bayes_replay(pts)
    assert abs(rep[-1]["mean"] - (1 + 5) / (2 + 50)) < 0.02  # concentration tends to K + prior
    # A long gap forgets the past: posterior drifts toward the new observations.
    pts2 = pts + [{"_ms": pts[-1]["_ms"] + 48 * HOUR, "p_long": 0.9, "n_eff": 50}]
    assert I.bayes_replay(pts2)[-1]["mean"] > 0.8
    s = I.bayes_summary(rep, 0.1)
    assert s["ci_low"] < s["posterior_mean"] < s["ci_high"]


def test_fear_greed_bands_and_missing():
    fg = I.fear_greed(funding_ann=0.0, p_post=0.5, rv_pct=0.5, ret_7d=0.0, sigma_d=0.02,
                      oi_change_24h=None, ret_24h=None)
    assert fg["score"] == 50.0 and fg["band"] == "NEUTRAL"
    assert "Open interest" in fg["missing"]
    fear = I.fear_greed(funding_ann=-0.5, p_post=0.05, rv_pct=0.99, ret_7d=-0.2, sigma_d=0.02,
                        oi_change_24h=None, ret_24h=None)
    assert fear["band"] == "EXTREME FEAR"


def test_accuracy_hit_rate_and_brier():
    candles = [{"t": i * HOUR, "T": (i + 1) * HOUR - 1, "c": 100 + i} for i in range(60)]
    prices = I.PriceLookup(candles, [])
    pts = [{"_ms": i * HOUR, "btc_mark": 100 + i, "p_long": 0.8, "verdict": "LONG"} for i in range(30)]
    acc = I.accuracy(pts, prices, now_ms=59 * HOUR)
    h1 = acc["horizons"]["1h"]
    assert h1["hit_rate"] == 1.0
    assert abs(h1["brier_raw"] - 0.04) < 1e-9


def test_contrarian_needs_sample():
    c = I.contrarian("SHORT", 0.08, {"extreme": {"24h": {"n": 5, "fade_hit_rate": 0.8}}})
    assert c["faded_verdict"] == "LONG"
    assert c["argues_for_fading"] is None
    assert c["extreme_now"] is True


def test_position_path_from_fills():
    fills = [
        {"coin": "BTC", "time": 10, "startPosition": "0", "sz": "2", "side": "B"},
        {"coin": "BTC", "time": 20, "startPosition": "2", "sz": "5", "side": "A"},
    ]
    path, vf = I.position_path(fills, -3.0, True, None)
    assert I.position_at(path, -3.0, 5, vf) == 0.0
    assert I.position_at(path, -3.0, 15, vf) == 2.0
    assert I.position_at(path, -3.0, 25, vf) == -3.0
    path2, vf2 = I.position_path(fills, -3.0, False, 8)
    assert I.position_at(path2, -3.0, 5, vf2) is None


def test_reconstruct_backtest_scores():
    candles = [{"t": i * HOUR, "T": (i + 1) * HOUR - 1, "c": 100 - i} for i in range(48)]
    wallets = [{"address": "a", "month_pnl": 1e6, "equity": 1e6, "szi": -1.0, "fills": [],
                "complete": True, "coverage_start": None}]
    bt = I.reconstruct_backtest(wallets, candles, 0, 47 * HOUR)
    assert bt["scores"]["4h"]["hit_rate"] == 1.0
    assert bt["follow_return"] > 0 > bt["hold_return"]


def test_x_sentiment_slot_absent_safe():
    assert I.x_sentiment_slot(None)["status"] == "PLANNED"
    assert I.x_sentiment_slot({"score": 3, "ts_utc": "t", "n_posts": 1})["status"] == "PLANNED"
    ok = I.x_sentiment_slot({"score": 0.2, "ts_utc": "t", "n_posts": 10})
    assert ok["status"] == "CONNECTED" and ok["data"]["score"] == 0.2


def test_grid_series_alignment():
    pts = [{"_ms": 0, "a": 1}, {"_ms": 60_000 * 30, "b": 2}, {"_ms": 60_000 * 90, "a": 3}]
    ga = I.grid_series(pts, 30 * 60_000, "a", 0, 60_000 * 90)
    gb = I.grid_series(pts, 30 * 60_000, "b", 0, 60_000 * 90)
    assert ga == [1.0, None, None, 3.0]
    assert gb == [None, 2.0, None, None]


def test_front_running_requires_significance():
    weak = {"lead_score": -0.5, "noise_band": 0.2, "peak": {"lag": -1, "r": -0.1}, "enough": True}
    assert I.front_running(weak)["label"] == "NO CLEAR LEAD"
    strong = {"lead_score": 0.6, "noise_band": 0.1, "peak": {"lag": 2, "r": 0.4}, "enough": True}
    assert I.front_running(strong)["label"] == "FRONT-RUNNING"


def test_squeeze_low_when_liquidations_far():
    obs = [{"address": f"s{i}", "btc_szi": -1.0, "btc_notional": 1e6, "equity": 1e5,
            "total_ntl": 1e6, "liquidation_px": 150.0, "month_pnl": 1e5} for i in range(5)]
    r = I.cohort_risk(obs, 100.0, 0.02, 0.05)
    assert r["squeeze"]["level"] == "LOW"
