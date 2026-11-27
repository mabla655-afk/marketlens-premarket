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
from data_source import parse_symbols, discover_candidate_universe
from morning_brief import morning_candidate, simulation_plan, simulate_exit_watch
from paper_signals import paper_signal, SIGNAL_BUY, SIGNAL_SELL, SIGNAL_WAIT, SIGNAL_UNAVAILABLE
from auto_dashboard import show_auto_tab
from mic_ui import show_mic_tab
from replay_ui import show_replay_tab
from mic_coach import previous_session, pivot_levels
from massive_data import fetch_many_preferred, fetch_history_preferred, fetch_massive_one
fetch_history_5m = fetch_history_preferred
from auto_store import is_cloud_database
from market_scanner import discover_massive, massive_key

st.set_page_config(page_title="MarketLens | Premarket Lab", page_icon="📈", layout="wide")

# A shared cloud database represents a single virtual account. Protect the UI;
# never expose DATABASE_URL or any market-data API key in GitHub.
if is_cloud_database():
    import os
    expected = os.environ.get('MARKETLENS_APP_PASSWORD','')
    if not expected:
        try:
            expected=str(st.secrets.get('MARKETLENS_APP_PASSWORD',''))
        except Exception:
            pass
    if not expected:
        st.error('Cloud database protection is not configured. Set MARKETLENS_APP_PASSWORD in Streamlit Secrets.')
        st.stop()
    import hmac
    if not st.session_state.get('_marketlens_authorized'):
        st.title('🔒 MarketLens — private paper account')
        pwd = st.text_input('App access password',type='password')
        if st.button('Unlock') and hmac.compare_digest(pwd,expected):
            st.session_state['_marketlens_authorized']=True
            st.rerun()
        elif pwd:
            st.warning('Enter the correct password and click Unlock.')
        st.stop()


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


def draw_intraday(intraday, prev_close, daily=None, today=None):
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
    # MIC Rock pivot guide: calculated strictly from the prior completed daily
    # candle, never from today's unfinished daily candle. Pure chart references.
    if daily is not None and today is not None:
        prior = previous_session(daily,today)
        if prior is not None:
            levels = pivot_levels(prior['high'],prior['low'],prior['close'])
            for label, color in [('P','#fbbf24'),('R1','#fb7185'),('S1','#2dd4bf')]:
                fig.add_hline(y=levels[label],line_dash='dashdot',line_width=1,
                              line_color=color,annotation_text='MIC '+label)
    fig.update_layout(height=480, margin=dict(l=8, r=8, t=20, b=10),
                      xaxis_title="Eastern Time", yaxis_title="USD (unadjusted)",
                      xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.08),
                      template="plotly_dark")
    return fig


now = datetime.now(ET)
st.title("☀️ MarketLens — Morning Trading Research")
st.caption("v0.8 · Morning Brief + automatic virtual simulator + interactive market replay · No real orders")

with st.sidebar:
    st.header("Morning setup")
    auto_discovery = st.toggle("Find active stocks automatically (experimental)", value=True,
        help="Uses Yahoo's general most-active and day-gainer screens as a candidate list; these are NOT dedicated premarket rankings or complete market coverage.")
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
    raw_tickers = st.text_area("Your own watchlist (up to 16)", value=", ".join(PRESETS[preset]), height=110,
                               help="The app checks this watchlist plus up to 12 automatically discovered names (16 combined maximum). Discovery is unofficial and may fail.",
                               key=f"watchlist_{preset}")
    scan_enabled = st.toggle("Auto refresh while I am viewing", value=True,
                             help="Refreshes roughly every 5 minutes while this page is open. Does not run background monitoring.")
    if scan_enabled:
        st_autorefresh(interval=300_000, key="marketlens_refresh")
    if st.button("Refresh provider data now", use_container_width=True):
        from data_source import fetch_one
        fetch_one.clear()
        fetch_massive_one.clear()
        fetch_history_preferred.clear()
        discover_candidate_universe.clear()
        st.rerun()
    st.divider()
    st.caption("Data source: Massive for both discovery AND OHLCV when API key is configured; otherwise unofficial Yahoo. Starter/Developer Massive feeds are 15-minute delayed. The app suppresses stale live signals.")
    st.caption("Book screening criteria are historical methods, not validated predictions. Paper research only.")
try:
    personal_symbols = parse_symbols(raw_tickers)
    if auto_discovery and massive_key() and 4 <= now.hour < 10 and now.time() < pd.Timestamp('09:30').time():
        discovery = discover_massive(now.replace(minute=(now.minute//5)*5,second=0,microsecond=0))
        discovery['explanation'] = discovery['source']
    else:
        discovery = discover_candidate_universe() if auto_discovery else {"symbols": [], "errors": [], "explanation": "Off"}
    symbols = list(dict.fromkeys(discovery["symbols"][:12] + personal_symbols))[:16]
    # Always retain open-position tickers in the automatic paper data feed, even
    # if Yahoo's daily discovery shortlist changes; otherwise exits are missed.
    try:
        from auto_store import load_state, get_engine
        saved_auto = load_state(get_engine())
        held = list(saved_auto.get('positions', {})) if saved_auto else []
        pending = list(saved_auto.get('pending', {})) if saved_auto else []
        symbols = list(dict.fromkeys(held + pending + symbols))[:16]
    except Exception:
        pass  # Account tab will show database diagnostics.

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
    st.info("Choose a starter watchlist or enable automatic candidate discovery in the sidebar.")
    st.stop()

st.download_button("Save my watchlist as JSON", json.dumps(personal_symbols, indent=2),
                   file_name="marketlens_watchlist.json", mime="application/json")

with st.spinner(f"Loading market observations for {len(symbols)} ticker(s)..."):
    results = fetch_many_preferred(symbols)

summaries = {s: source_table_row(s, results[s], now, is_session) for s in symbols}
paper_ideas = {s: paper_signal(results[s]["intraday"], now, regular_session_open=(status == "Regular session")) for s in symbols}
# The morning home screen stays intentionally short. Advanced research is in the second tab.
if "paper_journal" not in st.session_state:
    st.session_state["paper_journal"] = []
if "paper_positions" not in st.session_state:
    st.session_state["paper_positions"] = {}

brief_tab, auto_tab, replay_tab, mic_tab, research_tab = st.tabs(["☀️ START HERE", "🤖 PAPER SIM", "🎞️ MARKET REPLAY", "🧭 MIC COACH", "🔬 FULL RESEARCH"])

with auto_tab:
    show_auto_tab(now,status,results,summaries)

with replay_tab:
    show_replay_tab(symbols)


with brief_tab:
    st.subheader("Your morning briefing")
    st.caption("Research watchlist + a hypothetical plan. The app does not place trades or predict future prices.")
    if auto_discovery:
        st.caption(f"Auto-discovery: {len(discovery['symbols'])} candidate tickers. {discovery.get('explanation','')} "
                   "Every candidate is checked using the selected OHLCV provider. Freshness and subscription rights are checked independently; this is not a validated trading recommendation.")
        if discovery['errors']:
            with st.expander("Auto-discovery limitations"):
                for err in discovery['errors']:
                    st.warning(err)
    morning = [morning_candidate(s, summaries[s], now, status) for s in symbols]
    viable = [r for r in morning if r['rank'] >= 0 and r['label'] != 'Research only']
    viable.sort(key=lambda x: x['rank'], reverse=True)
    if status == 'Premarket':
        st.markdown("**Stocks to investigate before 9:30 a.m. ET**")
        if viable:
            st.dataframe(pd.DataFrame([{
                'Ticker': c['ticker'], 'Research status': c['label'],
                'Observed gap %': round(c['gap_pct'], 2),
                'Observed PM shares': c['volume'],
                'Last premarket bar (ET)': c['observed_at'].strftime('%I:%M %p'),
                'Why watch': c['note'],
            } for c in viable[:5]]), hide_index=True, use_container_width=True)
            st.caption("These are NOT buy recommendations. Verify the earnings/news catalyst, spread, price quality and data before trusting any pattern.")
        else:
            st.info("No current premarket candidate passed the basic observed-gap screening. This can mean missing/delayed data or simply no match. Nothing to simulate yet.")
        st.markdown("**When could a paper entry be considered?**")
        st.write("Wait for the first 5-minute candle after the 9:30 a.m. open. The app checks for a completed opening-range breakout, a close above VWAP, moving-average alignment and sufficient relative volume. The first possible confirmation is after 9:35 a.m.; the app can also say **WAIT**.")
    elif status == 'Regular session':
        st.markdown("**Research signals from completed 5-minute candles**")
        active = [{"Ticker": s, "Status": paper_ideas[s]['label'],
                   "Observed close": paper_ideas[s]['price'],
                   "Bar ended ET": (paper_ideas[s]['bar_end'].strftime('%I:%M %p') if paper_ideas[s]['bar_end'] else '—')}
                  for s in symbols if paper_ideas[s]['data_valid']]
        if active:
            st.dataframe(pd.DataFrame(active), hide_index=True, use_container_width=True)
        else:
            st.info("No verified fresh 5-minute signals at the moment. Wait for completed candles and check again.")
    else:
        st.info("The NYSE is not currently in its premarket window. No current morning picks are shown. The next U.S. market opening is displayed above.")

    st.divider()
    st.subheader("My paper-trading plan")
    with st.expander("Virtual account settings", expanded=False):
        virtual_cash = st.number_input("Virtual account balance ($)", min_value=100.0, max_value=1_000_000.0,
                                       value=10_000.0, step=500.0, key='brief_virtual_cash')
        virtual_risk = st.number_input("Maximum hypothetical risk per example (%)", min_value=0.1, max_value=5.0,
                                      value=0.5, step=0.1, key='brief_virtual_risk')
        virtual_cap = st.number_input("Maximum virtual account exposure per example (%)", min_value=1.0,
                                     max_value=100.0, value=10.0, step=1.0, key='brief_virtual_cap')
        st.caption("These values affect only virtual position-size math, not any real account. Paper fills, taxes, spreads and fees are not modeled.")
    suggestion_order = [s for s in symbols if paper_ideas[s]['label'] == SIGNAL_BUY]
    suggestion_order += [c['ticker'] for c in viable if c['ticker'] not in suggestion_order]
    suggestion_order += [s for s in symbols if s not in suggestion_order]
    brief_selected = st.selectbox("Stock to examine", suggestion_order, key='brief_select')
    brief_info = summaries[brief_selected]
    brief_idea = paper_ideas[brief_selected]
    brief_held = st.session_state['paper_positions'].get(brief_selected)
    b1, b2, b3 = st.columns(3)
    b1.metric("Observed price", '$'+fmt_number(brief_info['last_observed_price']) if brief_info['last_observed_price'] is not None else '—')
    b2.metric("Premarket gap", fmt_number(brief_info['premarket_gap_pct'], suffix='%'))
    b3.metric("5-min paper signal", brief_idea['label'])
    # Three immediately useful MIC research references on the beginner's home
    # screen. Do not claim they are validated entry/exit prices.
    previous = previous_session(results[brief_selected]['daily'], now.date())
    if previous:
        mic_levels = pivot_levels(previous['high'],previous['low'],previous['close'])
        with st.expander('🧭 MIC quick guide: yesterday’s chart reference levels'):
            lc1,lc2,lc3=st.columns(3)
            lc1.metric('Pivot (balance reference)',f"${mic_levels['P']:.2f}")
            lc2.metric('R1 (possible resistance)',f"${mic_levels['R1']:.2f}")
            lc3.metric('S1 (possible support)',f"${mic_levels['S1']:.2f}")
            st.caption(f"Calculated from the {previous['date']} completed daily candle using the supplied MIC Rock Pivot workbook. Not automatic buy/sell levels; see MIC COACH for explanations.")
    else:
        st.caption('MIC pivot levels: no validated prior-session OHLC available.')
    if status == 'Premarket':
        bars = results[brief_selected]['intraday']
        if not bars.empty:
            today_bars = as_et(bars)
            today_bars = today_bars.loc[(today_bars.index.date == now.date()) &
                (today_bars.index.time >= pd.Timestamp('04:00').time()) &
                (today_bars.index.time < pd.Timestamp('09:30').time()) &
                (today_bars.index <= pd.Timestamp(now))]
            if not today_bars.empty and brief_info['premarket_observed_at'] is not None:
                k1, k2, k3 = st.columns(3)
                k1.metric('Observed PM high', f"${today_bars['High'].max():.2f}")
                k2.metric('Observed PM low', f"${today_bars['Low'].min():.2f}")
                k3.metric('Previous session close', '$'+fmt_number(brief_info['prior_close']))
                st.caption('These are descriptive watch levels; they are not automatically buy, stop, or sell prices.')
        st.warning("**WAIT for the opening bell.** Premarket observations are watch levels, not an entry signal. "
                   "The virtual share count and exit examples require a fresh, confirmed setup after the open.")
    elif brief_idea['label'] == SIGNAL_BUY:
        st.success("**Simulated bullish setup detected.** This is a completed-candle research observation, not a prediction or real-money trade recommendation.")
    else:
        st.info(f"**{brief_idea['label']}** — {brief_idea['reason']}")

    plan = None
    if brief_idea['label'] == SIGNAL_BUY:
        # For this *illustrative* long setup use the nearest of the two supporting
        # technical observations as a notional invalidation reference.
        levels = [v for v in (brief_idea['range_low'], brief_idea['vwap'])
                  if v is not None and float(v) < brief_idea['price']]
        invalidation = max(levels) if levels else None
        plan = simulation_plan(brief_idea['price'], invalidation, virtual_cash, virtual_risk, virtual_cap)
        if plan is not None:
            st.markdown("**Hypothetical long-position worksheet — paper only**")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Virtual shares", f"{plan.shares}")
            m2.metric("Reference entry", f"${plan.entry_reference:.2f}")
            m3.metric("Review exit if below", f"${plan.invalidation_reference:.2f}")
            m4.metric("Illustrative 2R target", f"${plan.target_2r:.2f}")
            st.caption(f"Assumes {plan.shares} virtual shares and ${plan.virtual_notional:,.2f} virtual exposure; "
                       f"hypothetical risk to the invalidation level: ${plan.virtual_risk_at_level:,.2f}. "
                       "This is arithmetic from an observed candle, not a tradable quote or guaranteed exit. "
                       "The book's full context and news checks are NOT automated.")
            if plan.shares == 0:
                st.info("Your chosen virtual limits produce 0 simulated shares for this setup. No paper trade will be logged.")
        else:
            st.info("The technical reference levels do not form a usable example long-position worksheet.")

    if brief_held:
        st.markdown(f"**Open paper position:** {brief_held['qty']} virtual shares at a reference of ${brief_held['reference_entry']:.2f}.")
        st.info(simulate_exit_watch(brief_held, brief_idea))
    left_button, right_button = st.columns(2)
    with left_button:
        log_virtual_buy = st.button("Log simulated BUY", key='brief_paper_buy', use_container_width=True,
             disabled=not(plan and plan.shares > 0 and brief_idea['label'] == SIGNAL_BUY and brief_held is None),
             help="Only enabled for a fresh confirmed example. No brokerage action.")
    with right_button:
        log_virtual_sell = st.button("Log simulated SELL / CLOSE", key='brief_paper_sell', use_container_width=True,
             disabled=(brief_held is None or not brief_idea['data_valid']),
             help="Records an illustrative exit at the last completed candle close; not a real fill.")
    if log_virtual_buy and plan:
        st.session_state['paper_positions'][brief_selected] = {
            'qty': plan.shares, 'reference_entry': plan.entry_reference,
            'entered_bar': brief_idea['bar_end'].isoformat(),
            'invalidation_reference': plan.invalidation_reference,
            'target_2r': plan.target_2r,
        }
        st.session_state['paper_journal'].append({
            'Ticker': brief_selected, 'Action': 'PAPER BUY', 'Shares': plan.shares,
            'Reference price': plan.entry_reference, 'Bar end ET': brief_idea['bar_end'].isoformat(),
            'Simulated realized P/L': None, 'Context': 'Morning virtual worksheet'})
        st.rerun()
    if log_virtual_sell and brief_held:
        virtual_pnl = round((float(brief_idea['price']) - brief_held['reference_entry']) * brief_held['qty'], 2)
        st.session_state['paper_journal'].append({
            'Ticker': brief_selected, 'Action': 'PAPER SELL', 'Shares': brief_held['qty'],
            'Reference price': brief_idea['price'], 'Bar end ET': brief_idea['bar_end'].isoformat(),
            'Simulated realized P/L': virtual_pnl, 'Context': 'Morning virtual worksheet'})
        del st.session_state['paper_positions'][brief_selected]
        st.rerun()
    if st.session_state['paper_journal']:
        st.download_button('Download my virtual trade journal (CSV)',
            pd.DataFrame(st.session_state['paper_journal']).to_csv(index=False),
            file_name='marketlens_virtual_trade_journal.csv', mime='text/csv', key='brief_journal_csv')
        st.caption("The virtual journal is temporary browser-session storage. Download it before the session resets.")
    st.divider()
    st.caption("Market data: Massive when configured, otherwise unofficial Yahoo. Freshness and access vary by plan. "
               "The MIC COACH tab explains float, support/resistance and manual news checks. "
               "No live orders, guaranteed simulated fills or validated forecasts.")

with mic_tab:
    show_mic_tab(now, results, summaries, symbols)

with research_tab:
    rows = []
    for s in symbols:
        v = summaries[s]
        observation = v["last_observed_at"]
        rows.append({
            "Ticker": s,
            "Paper idea": paper_ideas[s]["label"],
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
    st.subheader("Paper-trading signal research")
    st.caption("v0.3: Simplified opening-range + VWAP + EMA + same-clock 5-minute relative-volume heuristics. Real historical/provider bars, but data may be delayed, incomplete or wrong. A signal is **not** a prediction, a complete BBT strategy, or a real-money recommendation. The app never sends orders to brokers.")
    paper_board = pd.DataFrame([{
        "Ticker": s,
        "Research label": paper_ideas[s]["label"],
        "Simulated reference price": paper_ideas[s]["price"],
        "Observed candle ended (ET)": paper_ideas[s]["bar_end"].strftime("%b %d %I:%M %p") if paper_ideas[s]["bar_end"] else "No current completed bar",
        "5-minute relative volume": paper_ideas[s]["relative_volume"],
        "Data freshness (min)": paper_ideas[s]["age_min"],
    } for s in symbols])
    st.dataframe(paper_board, hide_index=True, use_container_width=True,
                 column_config={"Simulated reference price": st.column_config.NumberColumn(format="$%.2f"),
                                "5-minute relative volume": st.column_config.NumberColumn(format="%.2fx"),
                                "Data freshness (min)": st.column_config.NumberColumn(format="%.1f")})
    st.info("'PAPER BUY CANDIDATE' and 'PAPER SELL / EXIT WATCH' are educational research labels only. 'SELL' means an observation potentially relevant to exiting a hypothetical long position; this demo does not model short selling. No signal means no paper action is suggested.")

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
        st.plotly_chart(draw_intraday(selected_data["intraday"], stats["prior_close"],selected_data["daily"],now.date()), use_container_width=True)
    else:
        st.warning("No intraday chart available for this ticker.")

    st.subheader("Selected ticker: paper signal & simulation")
    idea=paper_ideas[selected]
    if idea["label"] == SIGNAL_BUY:
        st.success(f"{idea['label']} — {idea['reason']}")
    elif idea["label"] == SIGNAL_SELL:
        st.warning(f"{idea['label']} — {idea['reason']}")
    else:
        st.info(f"{idea['label']} — {idea['reason']}")
    if idea["data_valid"]:
        a,b,c,d=st.columns(4)
        a.metric("Reference candle close",f"${idea['price']:.2f}")
        b.metric("Session VWAP",f"${idea['vwap']:.2f}")
        c.metric("EMA9 / EMA21",f"${idea['ema9']:.2f} / ${idea['ema21']:.2f}")
        d.metric("Relative candle volume",f"{idea['relative_volume']:.2f}x" if idea['relative_volume'] is not None else "Unavailable")
        with st.expander("See conditions used for this research label", expanded=False):
            st.dataframe(pd.DataFrame([{"Condition": k, "Result": "Pass" if v is True else "Not met" if v is False else "Not verifiable"}
                                       for k,v in idea['checks'].items()]),use_container_width=True,hide_index=True)
            st.caption(f"Reference is the **completed** 5-minute candle ending {idea['bar_end']:%b %d %I:%M %p ET}; freshness {idea['age_min']:.1f} minute(s). This is not an executable price or a guarantee of a simulated fill.")
        st.caption("The rule adds EMA9>EMA21 and same-clock relative-volume >=1.2 to an ORB/VWAP study. This is our own heuristic, **not** the complete setup in the book. No news/catalyst verification, Level 2 data, spread/fees, or validated win rate.")

    # Paper positions only live in this browser session. No brokerage integrations.
    if 'paper_journal' not in st.session_state:
        st.session_state['paper_journal'] = []
    if 'paper_positions' not in st.session_state:
        st.session_state['paper_positions'] = {}
    held = st.session_state['paper_positions'].get(selected)
    paper_qty = st.number_input("Hypothetical shares", min_value=1, max_value=1000, value=10, step=1,
                                 help="Paper-only quantity; this demo does not use or link any real funds.")
    col_buy,col_sell=st.columns(2)
    with col_buy:
        do_buy=st.button("Record simulated BUY",disabled=(idea['label']!=SIGNAL_BUY or held is not None),use_container_width=True,
                         help="Available only for a fresh qualifying paper BUY candidate and no existing position.")
    with col_sell:
        do_sell=st.button("Close simulated position (SELL)",disabled=(held is None or not idea['data_valid']),use_container_width=True,
                          help="Records a paper exit at the last observed completed candle close, not an actual fill.")
    if do_buy:
        qty=int(paper_qty)
        st.session_state['paper_positions'][selected]={"qty":qty,"reference_entry":float(idea['price']),"entered_bar":idea['bar_end'].isoformat()}
        st.session_state['paper_journal'].append({"Ticker":selected,"Action":"PAPER BUY","Shares":qty,"Reference price":float(idea['price']),
            "Bar end ET":idea['bar_end'].isoformat(),"Simulated realized P/L":None,"Context":idea['label']})
        st.success("Simulated entry recorded. No real order placed.")
        st.rerun()
    if do_sell and held is not None:
        qty=held['qty']
        pnl=round((float(idea['price'])-held['reference_entry'])*qty,2)
        st.session_state['paper_journal'].append({"Ticker":selected,"Action":"PAPER SELL","Shares":qty,"Reference price":float(idea['price']),
            "Bar end ET":idea['bar_end'].isoformat(),"Simulated realized P/L":pnl,"Context":idea['label']})
        del st.session_state['paper_positions'][selected]
        st.success("Simulated exit recorded; estimates ignore all fees/spreads and any price movement after the observed bar.")
        st.rerun()
    if held is not None:
        paper_change = ((float(idea['price'])-held['reference_entry'])*held['qty']) if idea['data_valid'] else None
        st.caption(f"**Open hypothetical position:** {held['qty']} shares at reference entry ${held['reference_entry']:.2f}. " +
                   (f"Unrealized simulated change based on a completed bar: ${paper_change:+,.2f}." if paper_change is not None else "Current mark unavailable."))
    if st.session_state['paper_journal']:
        with st.expander("Simulated trade journal (this browser session only)"):
            journal_df=pd.DataFrame(st.session_state['paper_journal'])
            st.dataframe(journal_df,hide_index=True,use_container_width=True)
            st.download_button("Download simulated trade log (CSV)",journal_df.to_csv(index=False),
                               file_name="marketlens_paper_journal.csv",mime="text/csv")
            st.caption("Save the CSV before leaving: Streamlit session state is not permanent storage and may reset on reconnect/redeployment.")

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

    st.caption("MarketLens v0.8 · Source-specific research from BBT and MIC materials · virtual practice only · provider data may be delayed")
