"""Historical, candle-by-candle educational replay. NEVER writes to paper account.

The visible chart, strategy checks and simulated state are rebuilt from a prefix
ending at the currently revealed 5-minute candle. Future bars are not passed to
signal generation. This is a study tool, not a predictive trading system.
"""
from __future__ import annotations
from datetime import date, datetime, time, timedelta
from typing import Any
import pandas as pd
from analytics import ET, as_et, tidy_ohlcv
from auto_simulator import replay_one_day, stats
from paper_signals import paper_signal, SIGNAL_BUY, SIGNAL_SELL, SIGNAL_WAIT
from book_strategies import orb_marks


def regular_bars_for_day(history: pd.DataFrame, day: date) -> pd.DataFrame:
    d=as_et(tidy_ohlcv(history)).sort_index()
    return d.loc[(d.index.date == day) & (d.index.time>=time(9,30)) & (d.index.time<time(16))]


def replay_dates(history: pd.DataFrame, asof: date | None = None, min_bars: int=3) -> list[date]:
    if history is None or history.empty:
        return []
    d=as_et(tidy_ohlcv(history))
    cutoff=asof or datetime.now(ET).date()
    options=[]
    for day, bars in d.groupby(d.index.date):
        regular=bars.loc[(bars.index.time>=time(9,30))&(bars.index.time<time(16))]
        # Never select today (potentially incomplete) or any day lacking the opening candle.
        if day < cutoff and len(regular)>=min_bars and regular.index[0].time()==time(9,30):
            options.append(day)
    return sorted(options,reverse=True)


def _plain_english(last: pd.Series, signal: dict, n: int, state: dict, bounds: dict) -> tuple[str,str,str]:
    if n == 1:
        return ("First five-minute candle completed",
                "The first candle establishes a reference high and low. No breakout is confirmed yet.",
                "Reveal the next candle and compare it with the opening range.")
    if state.get('positions'):
        p=next(iter(state['positions'].values()))
        return ("Virtual position open",
                f"The rule-based simulator holds {p['qty']} hypothetical shares. Entry, exit and risk levels are modeling assumptions—not available broker orders.",
                "Reveal the next candle to see whether its observed range intersects the simulated stop or target.")
    last_event=(state.get('events') or [{}])[-1]
    if last_event.get('type')=='PAPER CLOSE':
        return ("Virtual position closed", "A past candle crossed the simulated exit level. Results depend on synthetic fills and do not imply real execution.",
                "Review the event log to see how the hypothetical result was calculated.")
    if state.get('pending'):
        return ("A simulated entry is pending",
                "The earlier candle passed the simplified opening-range rules. A virtual entry is evaluated at the NEXT five-minute candle's open, not retroactively at the signal price.",
                "Reveal the next candle to test whether the paper entry actually occurs.")
    if n == 2:
        return ("Opening range established",
                f"The first candle's high and low ({bounds['high']:.2f} / {bounds['low']:.2f}) are now visible as reference levels. They are not forecasts.",
                "Continue one candle at a time. A pattern must meet ALL its measurable checks.")
    if signal['label']==SIGNAL_BUY:
        return ("Bullish study setup detected", "The completed candle meets the simplified research checks, but this is not necessarily an executed paper trade. See the pending-entry panel.",
                "Reveal the next candle to determine whether the existing simulator opens a hypothetical position.")
    if signal['label']==SIGNAL_SELL:
        return ("Bearish research condition", "Price is showing a bearish pattern in the simplified rules. This replay never opens short positions.",
                "Check the failed bullish conditions; wait for a different setup or record no trade.")
    if not signal.get('data_valid'):
        return ("Not enough validated data", signal['reason'], "Do not infer a hypothetical entry from missing candles or volume.")
    return ("Watch — no confirmed setup", "The completed candle does not meet all requirements. The model correctly has no simulated entry.",
            "Review which checks failed, then reveal the next candle.")


def replay_snapshot(history: pd.DataFrame, symbol: str, day: date, revealed: int, virtual_balance: float=10000.0) -> dict[str, Any]:
    """Produce a one-step teaching snapshot using *only* data available by this candle.

    Rebuild the paper simulator from the truncated history (independent of Neon).
    No future prices are passed into either the signal detector or engine.
    """
    if history is None or history.empty:
        raise ValueError('Historical 5-minute data is unavailable.')
    session=regular_bars_for_day(history,day)
    if session.empty or session.index[0].time()!=time(9,30):
        raise ValueError('Replay requires the opening 9:30 a.m. ET candle.')
    if not 1 <= int(revealed) <= len(session):
        raise ValueError('Reveal count outside available historical candles.')
    visible=session.iloc[:int(revealed)].copy()
    last_at=visible.index[-1]
    # Exclude *all* later candles, including later sessions, before passing into engine.
    prefix=as_et(tidy_ohlcv(history)).sort_index()
    prefix=prefix.loc[prefix.index<=last_at].copy()
    now=last_at.to_pydatetime()+timedelta(minutes=5)
    engine=replay_one_day(prefix,symbol,day,balance=virtual_balance)
    signal=paper_signal(prefix,now,regular_session_open=True)
    bounds=orb_marks(visible,day)
    heading,explanation,next_step=_plain_english(visible.iloc[-1],signal,len(visible),engine,bounds)
    closed=list(engine['closed_trades'])
    return dict(symbol=symbol,day=day,revealed=len(visible),total=len(session),visible=visible,asof=now,
                signal=signal,bounds=bounds,engine=engine,metrics=stats(engine),
                title=heading,explanation=explanation,next_step=next_step,
                done=(len(visible)==len(session)),closed=closed)


def classify_next_close(previous_close: float, next_close: float, threshold_pct: float=.1) -> str:
    """For a friendly optional learning quiz, not a trade signal."""
    if previous_close<=0 or next_close<=0:
        raise ValueError('Prices must be positive')
    change=(next_close/previous_close-1)*100
    if change>threshold_pct:
        return 'Higher'
    if change< -threshold_pct:
        return 'Lower'
    return 'About the same'
