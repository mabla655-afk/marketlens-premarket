"""Unofficial Yahoo market data. Do not use for order placement."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable
import pandas as pd
import streamlit as st
import yfinance as yf
from analytics import tidy_ohlcv

SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\^-]{0,11}$")


def parse_symbols(raw: str, max_symbols: int = 16) -> list[str]:
    candidates = re.split(r"[\s,;]+", raw.upper().strip())
    cleaned = list(dict.fromkeys(s for s in candidates if s))
    if len(cleaned) > max_symbols:
        raise ValueError(f"Use no more than {max_symbols} tickers per scan to reduce data-provider limits.")
    invalid = [s for s in cleaned if not SYMBOL_PATTERN.fullmatch(s)]
    if invalid:
        raise ValueError("Invalid ticker(s): " + ", ".join(invalid[:5]))
    return cleaned


@st.cache_data(ttl=270, show_spinner=False)
def fetch_one(symbol: str) -> dict:
    """Cached public-data request with independent history calls."""
    ticker = yf.Ticker(symbol)
    failures = []
    intraday = pd.DataFrame()
    daily = pd.DataFrame()
    try:
        intraday = tidy_ohlcv(ticker.history(period="5d", interval="5m", prepost=True, auto_adjust=False, actions=False, timeout=15))
    except Exception as exc:
        failures.append("5-minute bars unavailable: " + str(exc)[:140])
    try:
        daily = tidy_ohlcv(ticker.history(period="2y", interval="1d", prepost=False, auto_adjust=False, actions=False, timeout=15))
    except Exception as exc:
        failures.append("Daily bars unavailable: " + str(exc)[:140])
    if intraday.empty and daily.empty:
        failures.append("Provider returned no bars; symbol may be invalid, unavailable, or rate-limited.")
    return {"intraday": intraday, "daily": daily, "errors": failures}


def fetch_many(symbols: Iterable[str]) -> dict[str, dict]:
    symbols = list(symbols)
    result = {}
    with ThreadPoolExecutor(max_workers=min(3, max(1, len(symbols)))) as pool:
        futures = {pool.submit(fetch_one, ticker): ticker for ticker in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                result[symbol] = future.result()
            except Exception as exc:
                result[symbol] = {"intraday": pd.DataFrame(), "daily": pd.DataFrame(),
                                  "errors": [f"Could not fetch {symbol}: {str(exc)[:150]}"]}
    return result


@st.cache_data(ttl=1200, show_spinner=False)
def fetch_history_5m(symbol: str) -> dict:
    """Up to 60 days of 5-minute observations for descriptive ORB follow-through study.
    Data provider may return less history, missing sessions, or reject requests.
    """
    try:
        bars = yf.Ticker(symbol).history(period="60d", interval="5m", prepost=False,
                                         auto_adjust=False, actions=False, timeout=20)
        clean=tidy_ohlcv(bars)
        return {"bars":clean,"error":None if not clean.empty else "Provider returned no 5-minute history."}
    except Exception as exc:
        return {"bars":pd.DataFrame(),"error":str(exc)[:200]}


@st.cache_data(ttl=900, show_spinner=False)
def discover_candidate_universe() -> dict:
    """Yahoo's general market screeners, NOT a dedicated premarket scanner.

    Use them to select candidates for a *separate* current premarket-bar check.
    Yahoo screening results may reflect prior close/day-session prices and fail.
    """
    found, failures = [], []
    for screen in ("most_actives", "day_gainers"):
        try:
            payload = yf.screen(screen, count=12)
            quotes = payload.get("quotes", []) if isinstance(payload, dict) else []
            for row in quotes:
                symbol = row.get("symbol", "") if isinstance(row, dict) else ""
                if symbol and SYMBOL_PATTERN.fullmatch(symbol) and symbol not in found:
                    found.append(symbol)
        except Exception as exc:
            failures.append(f"{screen}: {str(exc)[:110]}")
    return {"symbols": found[:12], "errors": failures,
            "explanation": "Yahoo general active/gainers lists; NOT verified premarket winners."}
