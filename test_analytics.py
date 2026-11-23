from datetime import date, datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from analytics import (tidy_ohlcv, rsi, previous_regular_close,
                       premarket_statistics, backtest_pattern, watch_priority)

ET = ZoneInfo("America/New_York")


def daily_sample():
    index = pd.date_range("2026-08-03", periods=72, freq="B")
    close = 100 + np.linspace(0, 15, len(index)) + np.sin(np.arange(len(index)) / 3) * 3
    return pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                         "Close": close, "Adj Close": close, "Volume": [1_000_000] * len(index)}, index=index)


def intraday_sample():
    idx = pd.date_range("2026-11-20 04:00", periods=12, freq="5min", tz=ET)
    d = pd.DataFrame({"Open": 101., "High": 102., "Low": 100., "Close": 101.5, "Volume": 100}, index=idx)
    idx2 = pd.date_range("2026-11-23 04:00", periods=12, freq="5min", tz=ET)
    d2 = pd.DataFrame({"Open": 102., "High": 103., "Low": 101., "Close": 102.5, "Volume": 200}, index=idx2)
    return pd.concat([d, d2])


def test_previous_close_ignores_today():
    d = daily_sample()
    d.loc[pd.Timestamp("2026-11-23"), ["Open", "High", "Low", "Close", "Volume"]] = [200, 201, 199, 200, 100]
    prev = previous_regular_close(d, date(2026, 11, 23))
    assert prev != 200


def test_premarket_only_uses_today():
    d = daily_sample()
    obs = premarket_statistics(intraday_sample(), d,
                                datetime(2026, 11, 23, 5, 0, tzinfo=ET))
    assert obs["premarket_price"] == 102.5
    assert obs["premarket_volume"] == 2400
    assert obs["premarket_observed_at"].date() == date(2026, 11, 23)
    closed = premarket_statistics(intraday_sample(), d,
                                  datetime(2026, 11, 22, 5, 0, tzinfo=ET), is_trading_day=False)
    assert closed["premarket_price"] is None
    assert closed["last_observed_price"] is None


def test_returns_do_not_include_incomplete_day():
    d = daily_sample()
    s = backtest_pattern(d, "breakout_20", 5,
                         today=date(2026, 11, 23), include_today=False)
    assert isinstance(s["matches"], int)
    assert s["matches"] >= 0


def test_research_score_is_missing_without_observation():
    assert watch_priority({"premarket_gap_pct": None}) is None
    assert 0 <= watch_priority({"premarket_gap_pct": -3.4, "premarket_volume_ratio": 2}) <= 100


def test_rsi_flat_is_neutral():
    x = pd.Series([10.] * 40)
    assert rsi(x).iloc[-1] == 50.0
