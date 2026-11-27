"""Rule-based, educational *paper-only* stock setup observations.

Never send trades to a broker. These are simplified research heuristics influenced
by the opening-range and VWAP topics, not complete author-certified strategies.
Data freshness gates intentionally suppress actionable-looking labels on stale feeds.
"""
from __future__ import annotations

from datetime import datetime, time
import math
import numpy as np
import pandas as pd

from analytics import ET, add_indicators, as_et, tidy_ohlcv
from book_strategies import anchored_vwap, orb_marks


SIGNAL_BUY = "PAPER BUY CANDIDATE"
SIGNAL_SELL = "PAPER SELL / EXIT WATCH"
SIGNAL_WAIT = "WAIT / REVIEW"
SIGNAL_UNAVAILABLE = "NO CURRENT SIGNAL"


def _result(label: str, reason: str, **items) -> dict:
    return {"label": label, "reason": reason, "price": None, "bar_end": None,
            "age_min": None, "range_high": None, "range_low": None,
            "vwap": None, "ema9": None, "ema21": None, "relative_volume": None,
            "checks": {}, "data_valid": False, **items}


def _same_time_volume_baseline(regular: pd.DataFrame, day, bar_time: time) -> float | None:
    """Median prior-session volume at exact 5-min candle start, >=3 days required."""
    previous = regular.loc[(regular.index.date < day) & (regular.index.time == bar_time)]
    if previous.empty:
        return None
    v = previous.groupby(previous.index.date)["Volume"].sum()
    v = v[(v > 0) & np.isfinite(v)]
    return float(v.median()) if len(v) >= 3 and v.median() > 0 else None


def paper_signal(intraday: pd.DataFrame, now: datetime, regular_session_open: bool,
                 min_relative_volume: float = 1.2, max_bar_lag_minutes: int = 7) -> dict:
    """Signal from *completed* 5-min regular-session bars only.

    Last bar time is candle START and result bar_end is start+5 min.
    No short-selling mechanism. SELL is a bearish research idea/long exit watch.
    """
    now = now.astimezone(ET)
    if not regular_session_open or not (time(9, 35) <= now.time() < time(16)):
        return _result(SIGNAL_UNAVAILABLE, "Regular U.S. stock session is not open; no fresh paper-trading suggestions.")
    if intraday is None or intraday.empty:
        return _result(SIGNAL_UNAVAILABLE, "No intraday provider bars available.")
    d = as_et(tidy_ohlcv(intraday))
    if d.empty:
        return _result(SIGNAL_UNAVAILABLE, "No usable OHLCV data available.")
    regular = d.loc[(d.index.time >= time(9, 30)) & (d.index.time < time(16))].copy()
    # Do not use the currently forming bar (provider may timestamp candle starts).
    regular = regular.loc[regular.index + pd.Timedelta(minutes=5) <= pd.Timestamp(now)]
    today = regular.loc[regular.index.date == now.date()]
    if len(today) < 2 or today.index[0].time() != time(9, 30):
        return _result(SIGNAL_UNAVAILABLE, "First completed 5-minute opening-range candles are missing.")
    latest_at = today.index[-1]
    bar_end = latest_at + pd.Timedelta(minutes=5)
    age = max(0.0, (pd.Timestamp(now) - bar_end).total_seconds() / 60)
    if age > max_bar_lag_minutes:
        return _result(SIGNAL_UNAVAILABLE, f"Last completed regular-session candle ended {age:.0f} minutes ago, exceeding the {max_bar_lag_minutes}-minute freshness threshold.",
                       bar_end=bar_end.to_pydatetime(), age_min=age)
    # Missing same-session bars can cause a false impression of a new confirmed candle.
    if len(today) >= 2 and latest_at - today.index[-2] != pd.Timedelta(minutes=5):
        return _result(SIGNAL_UNAVAILABLE, "A 5-minute bar is missing immediately before the last candle; signal suppressed.",
                       bar_end=bar_end.to_pydatetime(), age_min=age)
    marks = orb_marks(today, now.date())
    if marks["high"] is None:
        return _result(SIGNAL_UNAVAILABLE, "Opening range is incomplete or its candles are missing.",
                       bar_end=bar_end.to_pydatetime(), age_min=age)
    indicators = add_indicators(regular)
    if len(indicators) < 21:
        return _result(SIGNAL_UNAVAILABLE, "Not enough completed regular-session history to calculate EMA21.",
                       bar_end=bar_end.to_pydatetime(), age_min=age)
    last = indicators.iloc[-1]
    vw = anchored_vwap(regular)
    if vw.empty or latest_at not in vw.index or not np.isfinite(vw.loc[latest_at]):
        return _result(SIGNAL_UNAVAILABLE, "Session VWAP unavailable or volume missing.",
                       bar_end=bar_end.to_pydatetime(), age_min=age)
    values = (last["Close"], last["EMA9"], last["EMA21"], last["Volume"])
    if not all(np.isfinite(v) for v in values) or float(last["Close"]) <= 0:
        return _result(SIGNAL_UNAVAILABLE, "Invalid or incomplete market data in the latest completed candle.")
    base = _same_time_volume_baseline(regular, now.date(), latest_at.time())
    relative_volume = float(last["Volume"] / base) if base and base > 0 else None
    price = float(last["Close"])
    vwap = float(vw.loc[latest_at])
    ema9, ema21 = float(last["EMA9"]), float(last["EMA21"])
    checks = {
        "Completed close above first 5-minute high": price > marks["high"],
        "Completed close below first 5-minute low": price < marks["low"],
        "Close above session VWAP": price > vwap,
        "Close below session VWAP": price < vwap,
        "EMA 9 above EMA 21": ema9 > ema21,
        "EMA 9 below EMA 21": ema9 < ema21,
        f"Relative 5-minute volume ≥ {min_relative_volume:g}x": None if relative_volume is None else relative_volume >= min_relative_volume,
        "Before 11:30 a.m. ET (morning entry window)": time(9, 40) <= bar_end.time() <= time(11, 30),
    }
    common = dict(price=price, bar_end=bar_end.to_pydatetime(), age_min=age,
                  range_high=marks["high"], range_low=marks["low"], vwap=vwap,
                  ema9=ema9, ema21=ema21, relative_volume=relative_volume,
                  checks=checks, data_valid=True)
    is_bull = all([checks["Completed close above first 5-minute high"],
                   checks["Close above session VWAP"], checks["EMA 9 above EMA 21"],
                   checks[f"Relative 5-minute volume ≥ {min_relative_volume:g}x"],
                   checks["Before 11:30 a.m. ET (morning entry window)"]])
    is_bear = all([checks["Completed close below first 5-minute low"],
                   checks["Close below session VWAP"], checks["EMA 9 below EMA 21"],
                   checks[f"Relative 5-minute volume ≥ {min_relative_volume:g}x"]])
    if is_bull:
        return _result(SIGNAL_BUY, "A bullish opening-range research setup meets the selected rule-based criteria. News, liquidity, and one-minute chart structure remain unverified.", **common)
    if is_bear:
        return _result(SIGNAL_SELL, "A bearish opening-range research setup meets the selected rule-based criteria. This is an exit watch for a hypothetical long position, not a short-sale order.", **common)
    if relative_volume is None:
        return _result(SIGNAL_WAIT, "Insufficient comparable historical 5-minute volumes to confirm the setup; do not treat this as a signal.", **common)
    return _result(SIGNAL_WAIT, "No fully confirmed rule-based opening-range paper setup. Continue observing and independently checking context.", **common)
