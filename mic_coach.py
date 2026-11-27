"""MIC-inspired educational research utilities.

Derived as short original summaries/calculations from user-provided MIC sheets and
handouts. Never routes orders, and does NOT turn subjective MIC short setups into
an automated strategy. An absent float, catalyst or filing is UNKNOWN, not false.
"""
from __future__ import annotations
from datetime import date
from math import floor, isfinite
from typing import Any
import pandas as pd

MIC_GLOSSARY = {
    "Float": "Shares generally available for public trading, not total shares outstanding. A smaller float can mean more abrupt moves.",
    "Float rotation": "Traded shares divided by float. It measures turnover, not how many unique people bought the shares.",
    "VWAP": "Average traded price weighted by volume for the selected session. Price above or below VWAP is context—not a prediction.",
    "Gap %": "The latest observed premarket price compared with the previous completed day's close.",
    "Premarket volume": "Shares reported traded before the 9:30 a.m. Eastern regular-market opening.",
    "Support / resistance": "Past price areas where trading has repeatedly paused or changed direction. They can fail.",
    "Pivot": "A reference level calculated from yesterday's high, low and close. It is not a forecast or automatic trade trigger.",
    "ATR": "Average true range: an estimate of recent daily price movement; not a direction predictor.",
    "Short interest": "The share of available float reported sold short. Data can be delayed and definitions differ by provider.",
    "Dilution": "The company issues shares or instruments that can increase shares outstanding. Verify recent filings rather than assuming from price action.",
    "Spread": "The difference between quoted bid and ask prices; wider spreads can make frequent simulated trades unrealistic.",
    "R (risk unit)": "Distance between a hypothetical entry and its invalidation reference multiplied by virtual shares.",
}

SOURCE_GUIDE = [
    ("MIC Checklist.docx", "Qualitative bullish/bearish factors; manual news, dilution, ownership and support review."),
    ("MIC Game-Plan.docx", "Three-ticker morning research worksheet with trend, news, float and planned levels."),
    ("MIC Rock Pivots.xlsx", "Exact reference-level formulas based on prior day high, low and close."),
    ("MIC Pos. Calc.xlsx", "Virtual-only example risk, reward, share and exposure calculations."),
    ("MIC Starter Pack (2023)", "Trading terminology, VWAP, support/resistance and float-rotation explanations."),
    ("TBradley90 Cheat Sheet", "Discretionary short-side cautions; never automatic short-selling decisions."),
    ("DAS Trader Pro instructions, hotkeys and layouts", "Reference only. No script, locate, hotkey or live order integration."),
    ("MIC 2024 flash calendar", "Inspiration for a dated learning journal—not reused as a 2026 market calendar."),
]


def _number(value: Any) -> float | None:
    try:
        n=float(value)
        return n if isfinite(n) else None
    except (TypeError,ValueError):
        return None


def pivot_levels(high: float, low: float, close: float) -> dict[str,float]:
    """Exactly reproduces formulas from @Modern_Rock Pivots.xlsx, B11:B24.

    Neither adjusted daily prices nor split-inconsistent H/L/C may be mixed.
    """
    h,l,c=(_number(x) for x in (high,low,close))
    if any(x is None for x in (h,l,c)) or not (0 < l <= c <= h):
        raise ValueError("Expected positive prior-session high >= close >= low")
    p=(h+l+c)/3
    r={
        'R1':2*p-l,
        'R2':p+h-l,
        'R3':2*p+h-2*l,
        'S1':2*p-h,
        'S2':p-(h-l),
        'S3':2*p-(2*h-l),
        'P':p,
    }
    for n in range(4,9):
        r[f'R{n}']=h+(n-1)*(p-l)
    for n in range(4,7):
        r[f'S{n}']=l-(n-1)*(h-p)
    return r


def previous_session(daily: pd.DataFrame, today:date) -> dict | None:
    """Prior day for *today's* plan; never mistake today's unfinished daily candle for yesterday."""
    if daily is None or daily.empty or not {'High','Low','Close'}.issubset(daily.columns):
        return None
    d=daily.sort_index()
    dates=pd.DatetimeIndex(d.index).date
    previous=d[dates<today]
    if previous.empty:
        return None
    row=previous.iloc[-1]
    high,low,close=(_number(row[k]) for k in ('High','Low','Close'))
    if any(v is None for v in (high,low,close)) or not 0<low<=close<=high:
        return None
    return {'date':str(pd.Timestamp(previous.index[-1]).date()),'high':high,'low':low,'close':close}


def float_rotation(traded_shares:float | None, float_shares:float | None) -> float | None:
    numerator,denominator=_number(traded_shares),_number(float_shares)
    if numerator is None or denominator is None or numerator<0 or denominator<=0:
        return None
    return numerator/denominator


def readable_context(summary:dict, float_shares:float|None=None, short_float_pct:float|None=None,
                     filing_status:str='Not checked', catalyst:str='Not checked') -> dict:
    """Human-readable *observations*, not a binary MIC strategy grade."""
    gap=_number(summary.get('premarket_gap_pct'))
    volume=_number(summary.get('premarket_volume'))
    rotation=float_rotation(volume,float_shares)
    price=_number(summary.get('last_observed_price'))
    observed=summary.get('premarket_observed_at')
    bullets=[]
    if gap is not None:
        bullets.append(f'Observed premarket move: {gap:+.1f}% versus the previous close. This is not the MIC 9:29 a.m. checkpoint.')
    else:
        bullets.append('Premarket move is unavailable: no directional conclusion.')
    if volume is not None:
        bullets.append(f'Observed premarket shares: {volume:,.0f}. High volume alone does not predict a direction.')
    else:
        bullets.append('Premarket volume is unavailable.')
    if rotation is not None:
        bullets.append(f'Premarket float turnover ≈ {rotation:.2f}x, based on manually supplied float ({float_shares:,.0f} shares).')
    else:
        bullets.append('Float rotation cannot be calculated until current float is verified.')
    if filing_status != 'Not checked':
        bullets.append('Filing/dilution review: '+filing_status+' (user-entered, unverified).')
    else:
        bullets.append('Share dilution and recent filings have not been verified.')
    if catalyst != 'Not checked':
        bullets.append('News context: '+catalyst+' (user-entered; verify original announcement).')
    else:
        bullets.append('News catalyst has not been verified.')
    caution=[]
    sf=_number(short_float_pct)
    if float_shares is not None and float_shares > 0 and float_shares <= 3_000_000:
        caution.append('MIC short-side caution: float at or below 3M; this is not an automated short setup.')
    if sf is not None and sf >= 20:
        caution.append('MIC short-side caution: reported short float at or above 20%; verify date and definition.')
    if gap is not None and gap >= 70:
        caution.append('MIC Checklist flags very large premarket rises as requiring bearish-factor review; this is not a sell signal.')
    return {'gap_pct':gap,'premarket_shares':volume,'observed_at':observed,'price':price,
            'float_rotation':rotation,'observations':bullets,'cautions':caution,
            'automation':'RESEARCH ONLY — subjective MIC factors are not automated trades'}


def virtual_position_example(balance:float, entry:float, stop:float, risk_pct:float=0.5,
                             max_exposure_pct:float=10, side:str='long') -> dict|None:
    """MIC worksheet-inspired arithmetic; virtual and educational only."""
    args=[_number(x) for x in [balance,entry,stop,risk_pct,max_exposure_pct]]
    if any(x is None for x in args):
        return None
    bal,e,s,risk,expo=args
    if bal<=0 or e<=0 or s<=0 or not (0<risk<=5 and 0<expo<=100) or side not in ('long','short'):
        return None
    distance=(e-s) if side=='long' else (s-e)
    if distance<=0:
        return None
    cap_risk=bal*risk/100
    cap_exposure=bal*expo/100
    shares=max(0,min(floor(cap_risk/distance),floor(cap_exposure/e)))
    target=e+(2*distance if side=='long' else -2*distance)
    return {'virtual_shares':shares,'risk_per_share':distance,'risk_at_stop':round(shares*distance,2),
            'virtual_notional':round(shares*e,2), 'two_r_reference':round(target,4),
            'risk_cap':round(cap_risk,2), 'exposure_cap':round(cap_exposure,2)}
