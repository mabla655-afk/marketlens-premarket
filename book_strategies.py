"""Interpretations of user-supplied BBT sources; research-only, never order signals.

Sources: Andrew Aziz, Advanced Techniques in Day Trading (2018), printed Ch 3 and Ch 6;
Bear Bull Traders TradeBook (2022), PDF pages specified in STRATEGY_LIBRARY.
Original paraphrases only. No trading advice or brokerage actions.
"""
from __future__ import annotations
from datetime import datetime, time, date
import numpy as np
import pandas as pd
from analytics import tidy_ohlcv, as_et, previous_regular_close, ET

STRATEGY_LIBRARY = [
    {"name":"Pre-market gappers screen", "source":"Aziz book, Chapter 3, printed pp. 80–83 (PDF pp. 88–91)",
     "status":"Measured filters + manual review", "summary":"Research filter: premarket gap, volume by 9 a.m., average daily turnover and ATR; news catalyst and chart quality need separate review.",
     "human":"Confirm a current news catalyst, relatively clean premarket action, technical levels, corporate actions and company float."},
    {"name":"5-minute Opening Range Breakout (ORB)", "source":"BBT TradeBook, PDF p. 7; Aziz book, Chapter 6 (Opening Range Breakout)",
     "status":"Boundary marker + descriptive history", "summary":"Use the first 9:30–9:35 candle as the opening range; note subsequent breaks above/below that range.",
     "human":"Check opening position relative to VWAP, volume, clean 1-minute structure, long wicks, chart levels and reward/risk."},
    {"name":"Fallen Angel / Rising Devil", "source":"BBT TradeBook, PDF p. 5; Aziz book, Chapter 6 (Fallen Angel)",
     "status":"Research checklist", "summary":"A gap in the prevailing trend, an opening pullback, and a rebound off a marked technical area.",
     "human":"Confirm catalyst, premarket trend, a support/resistance zone, reversal, increasing volume and no level blocking the move."},
    {"name":"ABCD / Reverse ABCD", "source":"BBT TradeBook, PDF p. 10; Aziz book, Chapter 6 (ABCD Pattern)",
     "status":"Research checklist", "summary":"A directional A-to-B leg, a roughly 40–70% pullback toward support/resistance, then a confirmed continuation.",
     "human":"Identify real pivot structure, confirmation candle, nearby 9 EMA / VWAP, technical levels and invalidation."},
    {"name":"Lightning Bolt", "source":"BBT TradeBook, PDF p. 11", "status":"Research checklist",
     "summary":"Trend continuation involving a move across VWAP, a retracement, and a renewed move through VWAP.",
     "human":"Check catalyst, float, contextual market trend, pullback volume, higher timeframe and VWAP closes."},
    {"name":"Extreme Reversal", "source":"BBT TradeBook, PDF p. 8", "status":"Research checklist",
     "summary":"Possible reversal with higher timeframe structure and 1-minute moving-average confirmation.",
     "human":"Check the 9/20 vs 50 SMA, fresh 5- and 15-minute extremes, 50 SMA retest and a confirming candle."},
    {"name":"Parabolic Reversal", "source":"BBT TradeBook, PDF p. 9", "status":"Research checklist",
     "summary":"Price becomes extended from the 5-minute 9 EMA and then shows a possible pullback toward it.",
     "human":"Assess extension, fresh 1-minute extremes, reversal candles and structure around the previous candle."},
    {"name":"Mountain Pass", "source":"BBT TradeBook, PDF p. 12", "status":"Research checklist",
     "summary":"A potential trend reversal with an unsuccessful second extreme and a subsequent 50 SMA cross.",
     "human":"Check double-top/bottom structure, higher context, catalyst, trend fatigue and confirmation candles."},
    {"name":"High/Low of Day at a round-number level", "source":"BBT TradeBook, PDF p. 13", "status":"Research checklist",
     "summary":"Study a high/low-of-day test near a significant whole-dollar price and adjacent technical levels.",
     "human":"Level 2/order-book conditions and the full event context are not available in the basic price feed."},
    {"name":"Bull Flag / Bear Flag", "source":"Aziz book, Chapter 6 (Bull Flag / Bear Flag)", "status":"Research checklist",
     "summary":"Look for a directional impulse followed by orderly consolidation and possible volume-backed continuation.",
     "human":"Confirm orderly consolidation, 1- and 5-minute structure, increasing volume and nearby resistance/support."},
    {"name":"VWAP Trading", "source":"Aziz book, Chapter 6 (VWAP Trading)", "status":"Research checklist + chart indicator",
     "summary":"Observe how price behaves around intraday volume-weighted average price.",
     "human":"Differentiate a sustained breakout, false breakout, reversal and simple VWAP proximity."},
    {"name":"1–2-minute Opening Range Breakdown", "source":"BBT TradeBook, PDF p. 4", "status":"Not specified in supplied TradeBook",
     "summary":"Listed in the TradeBook table of contents as coming soon.",
     "human":"No defined rules supplied here; not implemented."},
]


def atr14(daily: pd.DataFrame, asof: date | None = None) -> float | None:
    d = tidy_ohlcv(daily)
    if asof is not None:
        d = d.loc[pd.to_datetime(d.index).date < asof]
    if len(d) < 15:
        return None
    prev = d['Close'].shift(1)
    tr = pd.concat([d['High'] - d['Low'], (d['High'] - prev).abs(),
                    (d['Low'] - prev).abs()], axis=1).max(axis=1)
    out = tr.rolling(14, min_periods=14).mean().iloc[-1]
    return float(out) if np.isfinite(out) else None


def avg_daily_volume(daily: pd.DataFrame, asof: date | None = None, sessions: int = 20) -> float | None:
    d = tidy_ohlcv(daily)
    if asof is not None:
        d = d.loc[pd.to_datetime(d.index).date < asof]
    if len(d) < sessions:
        return None
    return float(d['Volume'].tail(sessions).mean())


def book_gapper_screen(intraday: pd.DataFrame, daily: pd.DataFrame, now: datetime,
                        is_trading_day: bool = True) -> dict:
    """Reproduce measurable Aziz Ch 3 criteria, never assume the news criterion.
    Volume criterion is measured by 9am ET, using 4:00–09:00 bars and at least
    one observed bar whose timestamp is 09:00 or later (partial early screening
    is marked pending); if observed at 9:00, 9:00 bar is *excluded*.
    """
    now = now.astimezone(ET)
    d = as_et(tidy_ohlcv(intraday))
    today = now.date()
    prev_close = previous_regular_close(daily, today)
    pm = d.loc[(d.index.date == today) & (d.index.time >= time(4)) & (d.index.time < time(9,30))] if is_trading_day else d.iloc[0:0]
    known_pm = pm.loc[pm.index <= pd.Timestamp(now)]
    pm_9 = known_pm.loc[known_pm.index.time < time(9)]
    latest_price = float(known_pm['Close'].iloc[-1]) if len(known_pm) else None
    gap = (latest_price/prev_close - 1)*100 if latest_price is not None and prev_close and prev_close>0 else None
    vol9 = int(pm_9['Volume'].fillna(0).sum()) if len(pm_9) else (0 if len(known_pm) else None)
    avgvol = avg_daily_volume(daily, today)
    atr = atr14(daily, today)
    volume_cutoff_reached = (now.time() >= time(9) and len(known_pm)>0 and
                             known_pm.index[-1].time() >= time(8,55))
    checks = {
        'Gap magnitude ≥ 2%': None if gap is None else abs(gap) >= 2.0,
        'PM volume ≥ 100K by 9:00 ET': None if not volume_cutoff_reached else vol9 >= 100_000,
        '20-day average volume > 500K': None if avgvol is None else avgvol > 500_000,
        '14-day ATR ≥ $0.50': None if atr is None else atr >= .50,
        'Verified news catalyst': None,
        'Clean price action / key levels': None,
    }
    return { 'gap_pct':gap, 'pm_volume_at_9':vol9 if volume_cutoff_reached else None,
             'avg_daily_volume_20': avgvol, 'atr14':atr, 'checks':checks,
             'automated_pass': all(v is True for k,v in checks.items() if k not in ('Verified news catalyst','Clean price action / key levels')),
             'all_checks_known': all(v is not None for v in checks.values()),
             'clock_at': now }


def anchored_vwap(regular: pd.DataFrame) -> pd.Series:
    """Per-session typical-price VWAP from 09:30 ET, reset each trading day."""
    d=as_et(tidy_ohlcv(regular))
    if d.empty: return pd.Series(dtype=float)
    r=d.loc[(d.index.time>=time(9,30)) & (d.index.time<time(16))].copy()
    if r.empty: return pd.Series(dtype=float)
    typical=(r['High']+r['Low']+r['Close'])/3
    pv=typical*r['Volume'].clip(lower=0)
    key=r.index.date
    v= pv.groupby(key).cumsum() / r['Volume'].clip(lower=0).groupby(key).cumsum().replace(0,np.nan)
    return v.rename('VWAP')


def orb_marks(frame: pd.DataFrame, day: date) -> dict:
    """5-minute completed-bar OR boundary markers, not precise fill/entry signals.
    The first bar is timestamped at 09:30, uses its high and low; subsequent
    completed candles are compared on close to avoid wick-only classifications.
    """
    d=as_et(tidy_ohlcv(frame))
    d=d.loc[(d.index.date==day) & (d.index.time>=time(9,30)) & (d.index.time<time(16))]
    empty={'high':None,'low':None,'events':[], 'status':'No complete opening range data'}
    if len(d)<2 or d.index[0].time()!=time(9,30): return empty
    if d.index[1].time() != time(9,35): return empty
    high=float(d['High'].iloc[0]); low=float(d['Low'].iloc[0]); events=[]
    for ts,row in d.iloc[1:].iterrows():
        if ts.time()>time(10,30): break
        # Close crossing boundary; one observation per direction per day.
        if row['Close']>high and (len(events)==0 or all(e['direction']!='Above range' for e in events)):
            events.append({'at':ts, 'direction':'Above range','close':float(row['Close'])})
        elif row['Close']<low and (len(events)==0 or all(e['direction']!='Below range' for e in events)):
            events.append({'at':ts, 'direction':'Below range','close':float(row['Close'])})
    return {'high':high,'low':low,'events':events,
            'status':'Opening range established' if not events else 'Observed boundary close(s)'}


def orb_history(frame: pd.DataFrame, today: date, forward_bars: int=3) -> dict:
    """Descriptive conditional follow-through, one first breakout close per session.
    No fills, exits, trading returns, slippage or false success claims.
    Skips missing/incomplete 5min candles and today to prevent lookahead.
    """
    if forward_bars not in (1,3,6):raise ValueError('forward_bars must be 1,3,6')
    d=as_et(tidy_ohlcv(frame))
    regular=d.loc[(d.index.time>=time(9,30))&(d.index.time<time(16))&(d.index.date<today)]
    rows=[]
    for session, group in regular.groupby(regular.index.date):
        if len(group)<forward_bars+2 or group.index[0].time()!=time(9,30):continue
        marks=orb_marks(group,session)
        if not marks['events']:continue
        event=marks['events'][0]
        loc=group.index.get_loc(event['at'])
        future=loc+forward_bars
        if future>=len(group):continue
        # Require bar continuity (5-minute bars, otherwise horizon is undefined).
        if group.index[future] - group.index[loc] != pd.Timedelta(minutes=5*forward_bars):continue
        at=float(event['close']); other=float(group['Close'].iloc[future]); direction=1 if event['direction']=='Above range' else -1
        move=(other/at-1)*100 if at>0 else None
        if move is not None and np.isfinite(move):
            rows.append({'Date':session.isoformat(),'Direction':event['direction'], 'Observed at (ET)':(event['at']+pd.Timedelta(minutes=5)).strftime('%H:%M'),
                         'Move after close %':round(move,3), 'Follow-through in same direction':bool(move*direction>0)})
    if not rows:return {'count':0, 'follow_through_pct':None,'median_directional_move_pct':None,'records':pd.DataFrame()}
    data=pd.DataFrame(rows)
    directional=np.where(data['Direction'].eq('Above range'),data['Move after close %'],-data['Move after close %'])
    return {'count':len(data), 'follow_through_pct':100*float(data['Follow-through in same direction'].mean()),
            'median_directional_move_pct':float(np.median(directional)),'records':data}
