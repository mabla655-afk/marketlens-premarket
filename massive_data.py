"""One consistent Massive OHLCV data source for book research and paper simulation.

Massive Starter/Developer are delayed. No fallback to Yahoo when a Massive key is
configured: mixing quote universes / timestamps invalidates a synthetic fill.
No orders, brokerage APIs or recommendations.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st
from analytics import ET
from market_scanner import massive_key
from market_data_format import parse_aggregate_rows
from data_source import fetch_many as yahoo_fetch_many, fetch_history_5m as yahoo_history, SYMBOL_PATTERN

API = 'https://api.massive.com'


def request_bars(symbol: str, multiplier: int, timespan: str, start: str, end: str,
                 key: str, timeout: int = 17) -> pd.DataFrame:
    """Request Massive bar aggregates, explicitly unadjusted for current price context."""
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError('Invalid symbol')
    url = f'{API}/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start}/{end}'
    response = requests.get(url, params={'apiKey': key, 'sort': 'asc', 'adjusted': 'false', 'limit': 50000}, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if payload.get('status') not in ('OK', 'DELAYED', None):
        raise RuntimeError('Market-data provider did not return a successful result')
    return parse_aggregate_rows(payload.get('results', []))


@st.cache_data(ttl=120, show_spinner=False)
def fetch_massive_one(symbol: str) -> dict:
    key = massive_key()
    if not key:
        return {'intraday': pd.DataFrame(), 'daily': pd.DataFrame(), 'errors': ['Missing Massive API key'], 'source': 'Massive'}
    today = datetime.now(ET).date()
    errors = []
    intraday = pd.DataFrame()
    daily = pd.DataFrame()
    try:
        intraday = request_bars(symbol, 5, 'minute', str(today-timedelta(days=17)), str(today), key)
    except Exception as e:
        code = getattr(getattr(e, 'response', None), 'status_code', None)
        errors.append(f'5-minute candles unavailable (HTTP {code or "network/data"})')
    try:
        daily = request_bars(symbol, 1, 'day', str(today-timedelta(days=150)), str(today), key)
    except Exception as e:
        code = getattr(getattr(e, 'response', None), 'status_code', None)
        errors.append(f'Daily candles unavailable (HTTP {code or "network/data"})')
    return {'intraday': intraday, 'daily': daily, 'errors': errors, 'source': 'Massive OHLCV',
            'warning': 'Entitlement may be 15-minute delayed; verify bar age on each run.'}


def fetch_many_preferred(symbols) -> dict:
    """Massive for all data when authorized; Yahoo only when no Massive key was configured."""
    symbols=list(dict.fromkeys(symbols))
    if not massive_key():
        result=yahoo_fetch_many(symbols)
        for val in result.values():
            val['source']='Yahoo unofficial (availability/delay varies)'
        return result
    results={}
    with ThreadPoolExecutor(max_workers=min(4,max(1,len(symbols)))) as pool:
        futures={pool.submit(fetch_massive_one, symbol):symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol=futures[future]
            try:
                results[symbol]=future.result()
            except Exception:
                results[symbol]={'intraday':pd.DataFrame(), 'daily':pd.DataFrame(),
                                 'errors':['Massive request failed'], 'source':'Massive OHLCV'}
    return results


@st.cache_data(ttl=900, show_spinner=False)
def fetch_history_preferred(symbol: str) -> dict:
    """Historical replay must use the same market-data source as the simulator."""
    if not massive_key():
        return yahoo_history(symbol)
    today=datetime.now(ET).date()
    try:
        bars=request_bars(symbol,5,'minute',str(today-timedelta(days=45)),str(today),massive_key())
        return {'bars':bars,'error':None if not bars.empty else 'No Massive history returned.'}
    except Exception as e:
        code=getattr(getattr(e,'response',None),'status_code',None)
        return {'bars':pd.DataFrame(),'error':f'Massive history unavailable (HTTP {code or "network/data"})'}
