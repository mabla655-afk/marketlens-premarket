"""Guardrails against false signals from future, closed or stale data."""
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from paper_signals import paper_signal, SIGNAL_BUY, SIGNAL_UNAVAILABLE, SIGNAL_WAIT

ET = ZoneInfo("America/New_York")


def synthetic(direction=1):
    dates = ["2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-23"]
    frames = []
    for i, day in enumerate(dates):
        idx = pd.date_range(f"{day} 09:30", periods=60 if i < 4 else 3, freq="5min", tz=ET)
        if i < 4:
            c = 100 + np.arange(len(idx)) * .02
            volume = np.full(len(idx), 2000)
        elif direction > 0:
            c = np.array([104.0, 105.0, 106.0])
            volume = np.array([2000, 2000, 4500])
        else:
            c = np.array([98.0, 97.0, 96.0])
            volume = np.array([2000, 2000, 4500])
        frames.append(pd.DataFrame({"Open":c, "High":c+.10, "Low":c-.10,
                                    "Close":c, "Volume":volume}, index=idx))
    return pd.concat(frames)


def test_bullish_rule_detectable_only_when_completed_and_fresh():
    d = synthetic()
    r = paper_signal(d, datetime(2026, 11, 23, 9, 46, tzinfo=ET), True)
    assert r["label"] == SIGNAL_BUY, r
    assert r["price"] == 106
    assert r["relative_volume"] == 2.25
    assert r["bar_end"].hour == 9 and r["bar_end"].minute == 45


def test_unfinished_candle_is_not_included():
    r = paper_signal(synthetic(), datetime(2026, 11, 23, 9, 42, tzinfo=ET), True)
    assert r["label"] != SIGNAL_BUY
    assert r["bar_end"] is None or r["bar_end"].minute <= 40


def test_no_signals_when_market_closed_or_old_or_no_data():
    d=synthetic()
    assert paper_signal(d, datetime(2026, 11, 23, 9, 46, tzinfo=ET), False)["label"]==SIGNAL_UNAVAILABLE
    assert paper_signal(d, datetime(2026, 11, 23, 11, 46, tzinfo=ET), True)["label"]==SIGNAL_UNAVAILABLE
    assert paper_signal(pd.DataFrame(), datetime(2026, 11, 23, 9, 46, tzinfo=ET), True)["label"]==SIGNAL_UNAVAILABLE


def test_volume_baseline_needed():
    d=synthetic()
    d=d[d.index.date>=datetime(2026,11,20).date()]
    result=paper_signal(d,datetime(2026,11,23,9,46,tzinfo=ET),True)
    assert result["label"] in (SIGNAL_WAIT,SIGNAL_UNAVAILABLE)


def test_no_leakage_from_future_bar():
    d = synthetic()
    future = pd.DataFrame({"Open":[200.],"High":[201.],"Low":[199.],"Close":[200.],"Volume":[1000000]},
                          index=pd.DatetimeIndex(["2026-11-23 10:00"],tz=ET))
    baseline=paper_signal(d,datetime(2026,11,23,9,46,tzinfo=ET),True)
    augmented=paper_signal(pd.concat([d,future]),datetime(2026,11,23,9,46,tzinfo=ET),True)
    assert augmented["price"] == baseline["price"]
    assert augmented["label"] == baseline["label"]
