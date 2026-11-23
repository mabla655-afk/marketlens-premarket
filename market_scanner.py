"""Optional broader Massive full-market premarket discovery.
Requires a paid subscription including this endpoint. Does not place orders.
Indicators & 5-minute simulation bars remain sourced from yfinance in v0.5.
"""
from __future__ import annotations
import os
from datetime import datetime, time, timezone
from math import isfinite
import requests
import streamlit as st
from analytics import ET
from data_source import SYMBOL_PATTERN


def massive_key():
    key=os.environ.get('MASSIVE_API_KEY','').strip()
    if not key:
        try:
            import streamlit as st
            key=str(st.secrets.get('MASSIVE_API_KEY','')).strip()
        except Exception:
            pass
    return key


def rank_full_market(items, now:datetime, limit=12):
    now=now.astimezone(ET)
    if not (time(4,0)<=now.time()<time(9,30)):
        return []
    ranked=[]
    for it in items:
        symbol=it.get('ticker','')
        if not isinstance(symbol,str) or not SYMBOL_PATTERN.fullmatch(symbol):
            continue
        gap=it.get('todaysChangePerc')
        trade=it.get('lastTrade') or {}
        minute=it.get('min') or {}
        previous=(it.get('prevDay') or {}).get('c')
        price=trade.get('p') or minute.get('c')
        vol=minute.get('av') or 0
        ts=trade.get('t') or minute.get('t')
        if not ts or not price or not previous or not gap:
            continue
        try:
            # Exchange trade timestamp generally in nanoseconds, minute aggregate in milliseconds.
            sec=float(ts)/(1e9 if float(ts)>1e16 else 1e3 if float(ts)>1e11 else 1)
            as_of=datetime.fromtimestamp(sec, timezone.utc).astimezone(ET)
            age=(now-as_of).total_seconds()/60
            gap=float(gap); price=float(price); previous=float(previous); vol=float(vol)
            if not (0<=age<=25 and as_of.date()==now.date() and isfinite(gap) and
                    5<=price<=500 and vol>=100_000 and abs(gap)>=2):
                continue
            if price/previous < .2 or price/previous > 5:
                continue
        except (ValueError,TypeError,OverflowError,ZeroDivisionError):
            continue
        score=abs(gap)*2 + min(30, vol/100_000)
        ranked.append(dict(ticker=symbol, premarket_gap_pct=gap, premarket_volume=int(vol),
                           observed_at=as_of, score=score))
    ranked.sort(key=lambda row:-row['score'])
    return ranked[:limit]


@st.cache_data(ttl=300, show_spinner=False)
def discover_massive(now):
    key=massive_key()
    if not key:
        return {'symbols':[], 'rows':[], 'errors':['MASSIVE_API_KEY is not configured.'],
                'source':'Massive full-market snapshot is off'}
    try:
        response=requests.get('https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers',
                              params={'apiKey':key}, timeout=25)
        response.raise_for_status()
        payload=response.json()
        rows=rank_full_market(payload.get('tickers',[]),now)
        return {'symbols':[r['ticker'] for r in rows], 'rows':rows, 'errors':[],
                'source':'Massive full-market snapshots; freshness/coverage depends on subscription'}
    except Exception as exc:
        # Never put API keys (embedded in request URLs) in user-facing diagnostics.
        status=getattr(getattr(exc,'response',None),'status_code',None)
        message=f'Massive request failed (HTTP {status}). Check API-key permissions and plan.' if status else 'Massive request failed. Check the connection, key, and plan.'
        return {'symbols':[], 'rows':[], 'errors':[message],
                'source':'Massive request failed'}
