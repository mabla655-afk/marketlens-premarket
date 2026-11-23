"""Pure, testable calculations for MarketLens. No brokerage or order execution."""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")
VALID_STUDIES = {
    "EMA 9 crosses above EMA 21": "ema_up",
    "EMA 9 crosses below EMA 21": "ema_down",
    "Close breaks above prior 20-day high": "breakout_20",
    "RSI 14 recovers above 30": "rsi_recover",
}


def tidy_ohlcv(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Validate OHLCV with timezone-aware DatetimeIndex where supplied."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = frame.copy()
    if isinstance(df.columns, pd.MultiIndex):
        # Some versions of yfinance return a one-symbol multi-index.
        df.columns = df.columns.get_level_values(0)
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [x for x in required if x not in df.columns]
    if missing:
        raise ValueError("Missing OHLCV columns: " + ", ".join(missing))
    df = df.loc[:, [x for x in [*required, "Adj Close"] if x in df.columns]].copy()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["Close"])
    df = df.loc[~df.index.duplicated(keep="last")].sort_index()
    return df


def as_et(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        # CSV inputs require explicit ET clock times, avoiding silent local TZ guesses.
        out.index = out.index.tz_localize(ET)
    else:
        out.index = out.index.tz_convert(ET)
    return out


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_gain = gains.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    result = result.mask((avg_gain == 0) & (avg_loss > 0), 0.0)
    result = result.mask((avg_gain == 0) & (avg_loss == 0), 50.0)
    return result


def add_indicators(frame: pd.DataFrame, use_adjusted: bool = False) -> pd.DataFrame:
    d = tidy_ohlcv(frame)
    if d.empty:
        return d
    close = d["Adj Close"] if use_adjusted and "Adj Close" in d.columns else d["Close"]
    d["EMA9"] = close.ewm(span=9, adjust=False, min_periods=9).mean()
    d["EMA21"] = close.ewm(span=21, adjust=False, min_periods=21).mean()
    d["RSI14"] = rsi(close)
    return d


def previous_regular_close(daily: pd.DataFrame, current_date: date) -> float | None:
    d = tidy_ohlcv(daily)
    if d.empty:
        return None
    previous = d.loc[pd.to_datetime(d.index).date < current_date]
    if previous.empty:
        return None
    return float(previous["Close"].iloc[-1])


def day_intraday(intraday: pd.DataFrame, day: date) -> pd.DataFrame:
    d = as_et(tidy_ohlcv(intraday))
    return d.loc[d.index.date == day]


def premarket_statistics(intraday: pd.DataFrame, daily: pd.DataFrame, now: datetime, is_trading_day: bool = True):
    """Today's 04:00–09:30 ET bars only; never substitute yesterday's quotes."""
    now = now.astimezone(ET)
    result = {"premarket_price": None, "premarket_volume": None, "premarket_gap_pct": None,
              "premarket_volume_ratio": None, "premarket_observed_at": None,
              "last_observed_price": None, "last_observed_at": None, "data_age_minutes": None,
              "prior_close": previous_regular_close(daily, now.date())}
    if not is_trading_day:
        return result
    d = as_et(tidy_ohlcv(intraday))
    current = d.loc[d.index.date == now.date()]
    if current.empty:
        return result
    latest = current.iloc[-1]
    latest_at = current.index[-1].to_pydatetime()
    result.update(last_observed_price=float(latest["Close"]), last_observed_at=latest_at,
                  data_age_minutes=max(0.0, (now - latest_at).total_seconds() / 60))
    pre = current.loc[(current.index.time >= time(4, 0)) & (current.index.time < time(9, 30))]
    if pre.empty:
        return result
    last_pre_at = pre.index[-1].to_pydatetime()
    result["premarket_price"] = float(pre["Close"].iloc[-1])
    result["premarket_volume"] = int(pre["Volume"].fillna(0).sum())
    result["premarket_observed_at"] = last_pre_at
    if result["prior_close"] and result["prior_close"] > 0:
        result["premarket_gap_pct"] = (result["premarket_price"] / result["prior_close"] - 1) * 100
    # Compare the same elapsed part of the premarket session, not whole historical days.
    cutoff = last_pre_at.time()
    earlier = d.loc[d.index.date < now.date()]
    earlier = earlier.loc[(earlier.index.time >= time(4, 0)) & (earlier.index.time <= cutoff)]
    if not earlier.empty:
        sums = earlier.groupby(earlier.index.date)["Volume"].sum()
        sums = sums[sums > 0].tail(8)
        if len(sums) >= 3 and sums.median() > 0:
            result["premarket_volume_ratio"] = result["premarket_volume"] / float(sums.median())
    return result


def daily_studies(daily: pd.DataFrame, today: date | None = None,
                  include_today: bool = False) -> pd.DataFrame:
    d = tidy_ohlcv(daily)
    if d.empty:
        return d
    if today is not None and not include_today:
        d = d.loc[pd.to_datetime(d.index).date < today].copy()
    d = add_indicators(d, use_adjusted=True)
    if d.empty:
        return d
    close = d["Adj Close"] if "Adj Close" in d.columns else d["Close"]
    d["ema_up"] = (d["EMA9"] > d["EMA21"]) & (d["EMA9"].shift(1) <= d["EMA21"].shift(1))
    d["ema_down"] = (d["EMA9"] < d["EMA21"]) & (d["EMA9"].shift(1) >= d["EMA21"].shift(1))
    d["breakout_20"] = close > close.shift(1).rolling(20, min_periods=20).max()
    d["rsi_recover"] = (d["RSI14"] >= 30) & (d["RSI14"].shift(1) < 30)
    for h in (1, 3, 5):
        d[f"forward_{h}d_pct"] = (close.shift(-h) / close - 1) * 100
    return d


def backtest_pattern(daily: pd.DataFrame, study_key: str, horizon: int = 5,
                     today: date | None = None, include_today: bool = False) -> dict:
    if study_key not in VALID_STUDIES.values():
        raise ValueError("Unknown study")
    if horizon not in (1, 3, 5):
        raise ValueError("Unsupported horizon")
    d = daily_studies(daily, today=today, include_today=include_today)
    key = f"forward_{horizon}d_pct"
    empty = {"matches": 0, "positive_pct": None, "median_pct": None, "p10_pct": None,
             "p90_pct": None, "unconditional_positive_pct": None, "unconditional_median_pct": None,
             "latest_completed_bar_matches": False, "examples": []}
    if d.empty or study_key not in d.columns:
        return empty
    all_forward = d[key].dropna()
    matched = d.loc[d[study_key].fillna(False), key].dropna()
    empty["latest_completed_bar_matches"] = bool(d[study_key].iloc[-1])
    empty["matches"] = int(len(matched))
    empty["unconditional_positive_pct"] = float((all_forward > 0).mean() * 100) if len(all_forward) else None
    empty["unconditional_median_pct"] = float(all_forward.median()) if len(all_forward) else None
    empty["examples"] = [str(pd.Timestamp(x).date()) for x in matched.tail(8).index]
    if len(matched):
        empty.update(positive_pct=float((matched > 0).mean() * 100),
                     median_pct=float(matched.median()), p10_pct=float(matched.quantile(.10)),
                     p90_pct=float(matched.quantile(.90)))
    return empty


def watch_priority(stats: dict) -> int | None:
    """Research sorting heuristic; NOT a return forecast, trade signal, or risk score."""
    gap = stats.get("premarket_gap_pct")
    if gap is None or not np.isfinite(gap):
        return None
    score = min(65, abs(float(gap)) * 9)
    relative = stats.get("premarket_volume_ratio")
    if relative is not None and np.isfinite(relative):
        score += min(35, max(0, (float(relative) - 1) * 12))
    return int(round(score))
