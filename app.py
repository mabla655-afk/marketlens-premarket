"""MarketLens: educational market monitoring and historical pattern research."""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from analytics import (ET, VALID_STUDIES, add_indicators, as_et, backtest_pattern,
                       premarket_statistics, watch_priority)
from book_strategies import (STRATEGY_LIBRARY, book_gapper_screen, anchored_vwap,
                             orb_marks, orb_history)
from data_source import fetch_many, parse_symbols, fetch_history_5m

st.set_page_config(page_title="MarketLens | Premarket Lab", page_icon="📈", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.3rem; max-width: 1500px;}
div[data-testid="stMetric"] {border: 1px solid #2e3e52; border-radius: 12px; padding: 10px 14px;}
header[data-testid="stHeader"] {background: transparent;}
.small-note {opacity: .8; font-size: .88rem;}
</style>
""", unsafe_allow_html=True)

PRESETS = {
    "Large-cap focus": ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA"],
    "Liquid ETFs": ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "SMH"],
    "Technology focus": ["NVDA", "AMD", "AAPL", "MSFT", "META", "GOOGL", "AVGO", "TSLA"],
    "Custom only": [],
}


def market_clock(now: datetime):
    cal = mcal.get_calendar("NYSE")
    schedule = cal.schedule(start_date=now.date() - timedelta(days=3), end_date=now.date() + timedelta(days=12))
    current = schedule.loc[schedule.index.date == now.date()]
    next_sessions = schedule.loc[schedule["market_open"] > pd.Timestamp(now).tz_convert("UTC")]
    next_open = next_sessions["market_open"].iloc[0].tz_convert(ET) if not next_sessions.empty else None
    if current.empty:
        return "Exchange closed (weekend or holiday)", False, next_open, None
    open_at = current["market_open"].iloc[0].tz_convert(ET)
    close_at = current["market_close"].iloc[0].tz_convert(ET)
    at = pd.Timestamp(now)
    if at < open_at.replace(hour=4, minute=0):
        phase = "Closed — premarket not started"
    elif at < open_at:
        phase = "Premarket"
    elif at < close_at:
        phase = "Regular session"
    elif at < close_at.replace(hour=20, minute=0):
        phase = "After-hours"
    else:
        phase = "Closed — session ended"
    return phase, True, next_open, close_at


def fmt_number(n, decimals=2, suffix=""):
    if n is None or not np.isfinite(n):
        return "—"
    return f"{n:,.{decimals}f}{suffix}"


def fmt_volume(n):
    if n is None or not np.isfinite(n):
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(int(n))


def source_table_row(symbol, item, now, is_session):
    intraday, daily = item["intraday"], item["daily"]
    info = premarket_statistics(intraday, daily, now, is_trading_day=is_session)
    screening=book_gapper_screen(intraday, daily, now, is_trading_day=is_session)
    info["book_gapper"] = screening
    info["research_priority"] = watch_priority(info)
    info["symbol"] = symbol
    return info


def draw_intraday(intraday, prev_close):
    d = add_indicators(as_et(intraday)).tail(900)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=d.index, open=d["Open"], high=d["High"],
                                 low=d["Low"], close=d["Close"], name="5-minute candles",
                                 increasing_line_color="#2dd4bf", decreasing_line_color="#fb7185"))
    if len(d) >= 21:
        fig.add_trace(go.Scatter(x=d.index, y=d["EMA9"], name="EMA 9", line=dict(color="#fbbf24", width=1.5)))
        fig.add_trace(go.Scatter(x=d.index, y=d["EMA21"], name="EMA 21", line=dict(color="#60a5fa", width=1.5)))
    # Session-reset VWAP: calculated from regular-session bars only.
    try:
        vw=anchored_vwap(d)
        if not vw.empty:
            fig.add_trace(go.Scatter(x=vw.index, y=vw.values, name="Session VWAP", line=dict(color="#a78bfa",width=1.6)))
        # Opening range levels are drawn for the most recent date with an actual 09:30 candle.
        for session in sorted(set(d.index.date), reverse=True):
            marks=orb_marks(d,session)
            if marks['high'] is not None:
                fig.add_hline(y=marks['high'], line_dash='dash', line_color='#31c48d', annotation_text=f'ORB high {session}')
                fig.add_hline(y=marks['low'], line_dash='dash', line_color='#f87171', annotation_text=f'ORB low {session}')
                break
    except Exception:
        pass  # Keep unadjusted candlesticks visible even when annotations cannot be computed.
    if prev_close and prev_close > 0:
        fig.add_hline(y=prev_close, line_dash="dot", line_color="#a3a3a3", annotation_text="Previous close")
    fig.update_layout(height=480, margin=dict(l=8, r=8, t=20, b=10),
                      xaxis_title="Eastern Time", yaxis_title="USD (unadjusted)",
                      xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.08),
                      template="plotly_dark")
    return fig


now = datetime.now(ET)
st.title("📈 MarketLens — Premarket Lab")
st.caption("v0.2 · Incorporates Andrew Aziz and Bear Bull Traders strategies · Research / paper testing only · No brokerage or automated orders")

with st.sidebar:
    st.header("Research universe")
    preset = st.selectbox("Starter watchlist", list(PRESETS))
    upload_watchlist = st.file_uploader("Import saved watchlist (.json)", type=["json"])
    if upload_watchlist is not None:
        try:
            raw_json = upload_watchlist.getvalue()
            signature = hashlib.sha256(raw_json).hexdigest() + preset
            if st.session_state.get("_last_imported_watchlist") != signature:
                imported = json.loads(raw_json.decode("utf-8"))
                if not isinstance(imported, list):
                    raise ValueError("JSON must be a list of symbols")
                st.session_state[f"watchlist_{preset}"] = ", ".join(parse_symbols(",".join(map(str, imported))))
                st.session_state["_last_imported_watchlist"] = signature
            st.success("Watchlist imported into the ticker field.")
        except Exception as exc:
            st.error("Invalid watchlist file: " + str(exc))
    raw_tickers = st.text_area("Tickers to scan (up to 16)", value=", ".join(PRESETS[preset]), height=110,
                               help="Only these symbols are scanned; this is not an exchange-wide top-gainers scanner.",
                               key=f"watchlist_{preset}")
    scan_enabled = st.toggle("Refresh when app is open", value=False,
                             help="Refreshes roughly every 5 minutes while this page is open. Does not run background monitoring.")
    if scan_enabled:
        st_autorefresh(interval=300_000, key="marketlens_refresh")
    if st.button("Refresh provider data now", use_container_width=True):
        from data_source import fetch_one
        fetch_one.clear()
        st.rerun()
    st.divider()
    st.caption("Data source: Yahoo Finance via unofficial yfinance interface. Intraday availability, completeness and delay vary. No uptime guarantee.")
    st.caption("Book screening criteria are historical methods, not validated predictions. Paper research only.")
try:
    symbols = parse_symbols(raw_tickers)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

status, is_session, next_open, close_time = market_clock(now)
meta1, meta2, meta3 = st.columns([1.6, 1.5, 2])
meta1.metric("U.S. equity session", status)
meta2.metric("Market clock", now.strftime("%a %b %d, %I:%M %p ET"))
meta3.metric("Next opening bell", next_open.strftime("%a %b %d, %I:%M %p ET") if next_open is not None else "Not available")

with st.expander("Important data interpretation", expanded=False):
    st.markdown("""
    - **Premarket gap** uses the last *observed* bar from today's 4:00–9:30 a.m. ET window vs. the prior completed regular-session close. It is **not** a price prediction.
    - **Premarket relative volume** compares observed premarket volume with the median of at least three prior premarket sessions, measured only up to the same clock time.
    - **Attention score** ranks unusual *observed* premarket movement and volume within your selected watchlist; it is not a buy/sell signal or success probability.
    - Prices may be delayed, missing, or incomplete. A closed market shows no fabricated premarket data.
    - The historical study uses daily data with corporate-action-adjusted closes when provided, and is **not** a tradable backtest. It does not model slippage, spreads, fees, or overlapping-signal dependence.
    """)

if not symbols:
    st.info("Enter one or more tickers in the sidebar to begin.")
    st.stop()

st.download_button("Save watchlist as JSON", json.dumps(symbols, indent=2),
                   file_name="marketlens_watchlist.json", mime="application/json")

with st.spinner(f"Loading market observations for {len(symbols)} ticker(s)..."):
    results = fetch_many(symbols)

summaries = {s: source_table_row(s, results[s], now, is_session) for s in symbols}
rows = []
for s in symbols:
    v = summaries[s]
    observation = v["last_observed_at"]
    rows.append({
        "Ticker": s,
        "Last observed price": v["last_observed_price"],
        "Last bar (ET)": observation.strftime("%b %d %H:%M") if observation else "No current-session bar",
        "Bar age (min)": int(round(v["data_age_minutes"])) if v["data_age_minutes"] is not None else None,
        "Premarket gap %": v["premarket_gap_pct"],
        "Premarket volume": v["premarket_volume"],
        "PM vol vs history": v["premarket_volume_ratio"],
        "Attention score": v["research_priority"],
        "Average daily volume (20d)": v["book_gapper"]["avg_daily_volume_20"],
        "ATR (14d)": v["book_gapper"]["atr14"],
        "Book gapper data": ("Measurable thresholds met; catalyst unverified" if v["book_gapper"]["automated_pass"] else "Incomplete / thresholds not all met"),
        "Feed": "Unavailable" if results[s]["intraday"].empty else "Unofficial / delay varies",
    })

st.subheader("Premarket monitoring board")
st.caption("Sorted by observed unusual activity, not by expected investment returns. '—' means the feed did not supply applicable current-session observations.")
board = pd.DataFrame(rows).sort_values(["Attention score", "Ticker"], ascending=[False, True], na_position="last")
st.dataframe(board, use_container_width=True, hide_index=True,
             column_config={
                "Last observed price": st.column_config.NumberColumn(format="$%.2f"),
                "Premarket gap %": st.column_config.NumberColumn(format="%.2f%%"),
                "Premarket volume": st.column_config.NumberColumn(format="%d"),
                "PM vol vs history": st.column_config.NumberColumn(format="%.2fx"),
                "Attention score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
                "Bar age (min)": st.column_config.NumberColumn(format="%d"),
                "ATR (14d)": st.column_config.NumberColumn(format="$%.2f"),
                "Average daily volume (20d)": st.column_config.NumberColumn(format="%.0f"),
             })
st.download_button("Export monitoring board (CSV)", board.to_csv(index=False),
                   file_name=f"marketlens_scan_{now:%Y%m%d}.csv", mime="text/csv")
failures = [f"{symbol}: {'; '.join(item['errors'])}" for symbol, item in results.items() if item["errors"]]
if failures:
    with st.expander(f"Provider diagnostics ({len(failures)} ticker(s))"):
        for msg in failures:
            st.warning(msg)

st.divider()
st.subheader("Detailed ticker research")
selected = st.selectbox("Select a ticker", symbols)
selected_data = results[selected]
stats = summaries[selected]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Last observed price", "$" + fmt_number(stats["last_observed_price"]) if stats["last_observed_price"] is not None else "—")
m2.metric("Today's premarket gap", fmt_number(stats["premarket_gap_pct"], suffix="%"))
m3.metric("Today's premarket volume", fmt_volume(stats["premarket_volume"]))
m4.metric("Premarket vs prior sessions", fmt_number(stats["premarket_volume_ratio"], suffix="×"))
if stats["last_observed_at"]:
    st.caption(f"Last bar observed at {stats['last_observed_at']:%b %d, %Y %I:%M %p ET}. Bars may be delayed. Data age: {stats['data_age_minutes']:.0f} min.")
else:
    st.info("No current-session intraday bar. The market may be closed, or the data provider may be unavailable.")

if not selected_data["intraday"].empty:
    st.plotly_chart(draw_intraday(selected_data["intraday"], stats["prior_close"]), use_container_width=True)
else:
    st.warning("No intraday chart available for this ticker.")

st.subheader("Book-based premarket investigation")
st.caption("Andrew Aziz, *Advanced Techniques in Day Trading*, Chapter 3, printed pp. 80–83. This checks your custom watchlist—not all listed U.S. stocks.")
book_screen=stats["book_gapper"]
book_rows=[]
for criterion, passed in book_screen["checks"].items():
    book_rows.append({"Condition":criterion,"Observed status":"Meets threshold" if passed is True else "Does not meet" if passed is False else "Needs data / manual review"})
st.dataframe(pd.DataFrame(book_rows),hide_index=True,use_container_width=True)
st.caption("The source specifies 2% gap, 100K premarket shares by 9 a.m. ET, >500K average daily shares, ATR of at least $0.50, plus a real news catalyst. Implementation assumes 20 prior sessions for average volume and a 14-day simple ATR. Missing or early data are NOT counted as passing. News and chart quality require human verification.")

st.subheader("5-minute Opening Range — BBT TradeBook")
st.caption("BBT TradeBook p. 7: first 09:30–09:35 ET candle. This tool marks *bar-close observations*, not the book's full entry and management rules.")
if not selected_data["intraday"].empty:
    # Yahoo bars are timestamped by their START; exclude the unfinished current candle.
    completed = as_et(selected_data['intraday'])
    completed = completed.loc[completed.index + pd.Timedelta(minutes=5) <= pd.Timestamp(now)]
    observed=orb_marks(completed,now.date())
    if observed['high'] is None:
        st.info("No usable 09:30–09:35 ET range for the current session. This is normal before the open, on holidays and weekends, or when provider bars are missing.")
    else:
        oa,ob,oc=st.columns(3)
        oa.metric('Range high',f"${observed['high']:.2f}")
        ob.metric('Range low',f"${observed['low']:.2f}")
        oc.metric('Observed boundary closes',len(observed['events']))
        for event in observed['events']:
            st.write(f"• {(event['at'] + pd.Timedelta(minutes=5)):%H:%M} ET: 5-minute candle closed {event['direction'].lower()} at ${event['close']:.2f}.")
        st.caption("Not a verified book setup: clean 1-minute action, volume context, VWAP position and chart-level judgment are not automatically confirmed.")
else:
    st.info('Intraday feed unavailable, so opening range observations cannot be calculated.')

with st.expander("Explore the last 60 days of 5-minute opening-range observations",expanded=False):
    horizon_bars=st.selectbox('Measure change after', [1,3,6],index=1,
                          format_func=lambda x: f'{x*5} minutes after the first observed breakout close')
    if st.button(f'Fetch intraday history for {selected}',key=f'orb_fetch_{selected}'):
        st.session_state[f'orb_loaded_{selected}']=True
    if st.session_state.get(f'orb_loaded_{selected}'):
        with st.spinner('Loading selected ticker 5-minute history...'):
            historical=fetch_history_5m(selected)
        if historical['error']:
            st.warning('Unable to study this ticker: '+historical['error'])
        else:
            study_orb=orb_history(historical['bars'],now.date(),forward_bars=horizon_bars)
            if not study_orb['count']:
                st.info('No qualifying complete historical session and forward horizon in provider data.')
            else:
                aa,bb,cc=st.columns(3)
                aa.metric('Sessions with observed first break',study_orb['count'])
                bb.metric('Same-direction close after horizon',f"{study_orb['follow_through_pct']:.1f}%")
                cc.metric('Median directional move after horizon',f"{study_orb['median_directional_move_pct']:.2f}%")
                st.dataframe(study_orb['records'],hide_index=True,use_container_width=True)
                st.download_button('Export historical observations (CSV)',study_orb['records'].to_csv(index=False),
                                   file_name=f'marketlens_orb_{selected}.csv',mime='text/csv')
                st.warning('This is descriptive pattern follow-through, NOT backtested trading performance or a probability forecast. Data may be sparse. Includes no fills, trading costs, slippage, spreads, timing delays or selection-bias corrections.')

st.subheader("Historical daily-pattern study (separate from book-defined setups)")
st.caption("A descriptive study of prior daily patterns—not a forward-looking probability or advice to trade.")
left, right = st.columns([2.3, 1])
with left:
    label = st.selectbox("Historical pattern", list(VALID_STUDIES))
with right:
    horizon = st.selectbox("Forward horizon", [1, 3, 5], index=2, format_func=lambda x: f"{x} trading day(s)")

if not selected_data["daily"].empty:
    include_today = bool(is_session and close_time and pd.Timestamp(now) >= close_time)
    study = backtest_pattern(selected_data["daily"], VALID_STUDIES[label], horizon,
                             today=now.date(), include_today=include_today)
    if study["matches"] == 0:
        st.info("No complete historical matches found for this pattern and time horizon in the available data.")
    else:
        cols = st.columns(4)
        cols[0].metric("Historical matches", str(study["matches"]))
        cols[1].metric("Observed positive closes", fmt_number(study["positive_pct"], 1, "%"))
        cols[2].metric("Median forward move", fmt_number(study["median_pct"], 2, "%"))
        cols[3].metric("10th–90th percentile", f"{study['p10_pct']:.2f}% to {study['p90_pct']:.2f}%")
        st.caption(f"For comparison, all eligible days in this ticker's data had {fmt_number(study['unconditional_positive_pct'], 1, '%')} positive closes and a {fmt_number(study['unconditional_median_pct'], 2, '%')} median {horizon}-day change.")
        st.write("**Latest completed session matches pattern:** " + ("Yes" if study["latest_completed_bar_matches"] else "No"))
        st.write("**Recent matching dates:** " + (", ".join(study["examples"]) if study["examples"] else "None"))
        if study["matches"] < 30:
            st.warning("Small sample: fewer than 30 historical matches. Treat these statistics as particularly unstable.")
        st.caption("Signals can overlap; these outcomes are not independent. No transaction costs, spread, executions, or survivorship corrections are modeled.")
else:
    st.info("Historical daily bars were not available for this ticker.")

st.divider()
notes_tab, resources_tab, method_tab = st.tabs(["Investigation notes", "Research links", "Strategy library from your PDFs"])
with notes_tab:
    st.write("Make notes while reviewing earnings, catalysts, liquidity, sector context, and what could invalidate a pattern.")
    note = st.text_area("Research journal", placeholder="Example: What news is driving interest? What data is missing? What is the counterargument?", height=140)
    if note.strip():
        st.download_button("Export this note", f"Ticker: {selected}\nDate: {now.isoformat()}\n\n{note}",
                           file_name=f"marketlens_notes_{selected}_{now:%Y%m%d}.txt", mime="text/plain")
    st.caption("Notes are not saved automatically between browser sessions. Export them to keep a copy.")
with resources_tab:
    st.markdown(f"- [Yahoo Finance quote and news](https://finance.yahoo.com/quote/{selected}/) (third-party provider)\n- [SEC EDGAR company filings search](https://www.sec.gov/edgar/search/)\n- [Nasdaq market activity](https://www.nasdaq.com/market-activity)")
    st.write("Review the company's recent filings, earnings calendar, market news, share structure, and the timestamp of any quoted data before drawing conclusions.")
with method_tab:
    st.write("These are concise interpretations of the **two PDFs you supplied**. The whole books are not copied into the app. The labels distinguish automatic observations from setups that require discretion.")
    st.dataframe(pd.DataFrame([{"Strategy":x['name'], "Source":x['source'],"Implementation":x['status']} for x in STRATEGY_LIBRARY]),
                 hide_index=True,use_container_width=True)
    item=st.selectbox('Open strategy research checklist',[s['name'] for s in STRATEGY_LIBRARY])
    detail=next(s for s in STRATEGY_LIBRARY if s['name']==item)
    st.markdown('**Concept:** '+detail['summary'])
    st.markdown('**Manual verification needed:** '+detail['human'])
    st.caption(detail['source'])
    st.info('The book emphasizes trader discretion; software only flags observable conditions. A pattern is not a recommendation or a verified advantage.')

st.caption("MarketLens v0.2 · Derived research criteria from user-supplied books · unofficial Yahoo Finance data · paper-research only")
