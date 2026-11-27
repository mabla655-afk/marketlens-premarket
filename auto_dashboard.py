"""Minimal automatic virtual-simulator UI. Never transmits broker orders."""
from __future__ import annotations
from datetime import datetime, time
import json
import pandas as pd
import streamlit as st
from auto_store import (new_account, get_engine, load_state, save_state,
                        is_cloud_database, export_state)
from auto_simulator import (advance_account, select_research_watch, equity, stats, replay_one_day, event)
from analytics import ET


def show_auto_tab(now, status, results, summaries):
    st.header('🤖 Automatic paper-trading practice')
    st.caption('Virtual-only · No brokerage connection · No real buys or sells. This engine uses only the existing simplified long-only BBT opening-range rule; the new MIC research tab does NOT trigger automatic shorts.')
    with st.expander('📘 Beginner guide: what do these numbers mean?', expanded=False):
        st.markdown('''
        **Price** is what a stock last traded for; it is not a guaranteed next price.\n\n
        **Volume** is the number of shares traded in a period. Higher than usual volume may indicate attention, not a reliable upward move.\n\n
        **Premarket gap** compares an observed premarket price to yesterday’s close.\n\n
        **VWAP** is an average price weighted by trading volume, often used as a reference line.\n\n
        **Opening-range breakout** is a chart observation after 9:35 a.m. ET, when price moves beyond the first five-minute range.\n\n
        **Virtual shares** are calculated from the practice account's risk and exposure limits. A stop or target is only a simulated reference.
        ''')
        st.info('Suggested routine: 9:00 ET review the watchlist; 9:30 ET observe the open; after 9:40 ET check paper-only rules; after 4:00 ET review the journal. No number of trades is required.')
    if not is_cloud_database():
        st.warning('Local SQLite mode: paper records are saved in this app instance, but Streamlit Community Cloud can erase local files at restart. Connect external PostgreSQL before relying on lasting records or unattended scheduling.')
    else:
        st.success('External PostgreSQL configured. Keep the website access-controlled and configure GitHub Actions secrets for scheduled runs.')
    try:
        db=get_engine()
        state=load_state(db)
    except Exception as exc:
        st.error('Could not connect to the paper account database: '+str(exc)[:180])
        return
    if state is None:
        st.info('Create your virtual account first. No real financial account or brokerage login is required.')
        balance=st.number_input('Initial virtual balance ($)', min_value=1000, max_value=1000000,
                                value=10000, step=1000, key='auto_initial_balance')
        if st.button('Create virtual account', type='primary'):
            save_state(db,new_account(float(balance),now))
            st.rerun()
        return
    import os
    scheduler_flag=os.environ.get('MARKETLENS_USE_SCHEDULER','').lower()=='true'
    if not scheduler_flag:
        try:
            scheduler_flag = str(st.secrets.get('MARKETLENS_USE_SCHEDULER','false')).lower()=='true'
        except Exception:
            pass
    if scheduler_flag:
        st.caption('Unattended mode configured: the GitHub Actions job updates the virtual account. This page displays the saved account and does not run duplicate simulations.')
    top_left,top_right=st.columns([2,1])
    with top_left:
        st.markdown('**Mode:** '+('🟢 Automatic simulation enabled' if state['enabled'] else '⚪ Paused'))
        if state['enabled']:
            if st.button('Pause automatic paper simulation', disabled=bool(state['positions'])):
                state['enabled']=False
                save_state(db,state)
                st.rerun()
            if state['positions']:
                st.caption('Pause is disabled while virtual positions are open so end-of-day monitoring is not interrupted.')
        else:
            if st.button('Activate fully automatic PAPER simulation',type='primary'):
                state['enabled']=True
                state['activated_at']=now.isoformat()
                state['pending']={}
                state['last_processed']={}
                state['watch_by_day']={}
                event(state,'ACTIVATED',now,detail='Virtual-only, no broker orders')
                save_state(db,state)
                st.rerun()
    with top_right:
        st.caption('Automatic decisions are intentionally conservative: max two virtual entries/day, only fresh 5-minute bars, no trades without a confirmed setup.')

    day=now.date().isoformat()
    # Always watch positions, even if no new candidates qualify for the day.
    if state['enabled'] and not scheduler_flag and status in ('Premarket','Regular session') and day not in state['watch_by_day']:
        if time(9,0) <= now.time() <= time(9,35):
            watch=select_research_watch(summaries,now.date(),now=now)
            if watch:
                state['watch_by_day'][day]=watch
                event(state,'WATCHLIST',now,detail=', '.join(watch))
                save_state(db,state)
    symbols=state['watch_by_day'].get(day,[])
    if state['enabled'] and not scheduler_flag and status=='Regular session':
        before=json.dumps(state,sort_keys=True)
        state=advance_account(state,{k:v['intraday'] for k,v in results.items()},now)
        if json.dumps(state,sort_keys=True)!=before:
            save_state(db,state)
    marks={k:summaries[k].get('last_observed_price') for k in state['positions'] if k in summaries}
    marks={k:v for k,v in marks.items() if v and pd.notna(v)}
    s=stats(state)
    equity_now=equity(state,marks)
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Virtual equity',f'${equity_now:,.2f}',f'${equity_now-state["starting_balance"]:+,.2f}')
    c2.metric('Available virtual cash',f'${state["cash"]:,.2f}')
    c3.metric('Completed paper trades',s['closed_trades'])
    c4.metric('Realized win rate',f'{s["win_rate"]:.0f}%' if s['win_rate'] is not None else 'Not enough trades')
    st.caption('Equity uses latest observed prices, which may be stale; drawdown below uses realized closed trades only. Nothing here is a forecast.')
    from market_scanner import massive_key
    if massive_key():
        st.caption('Price feed: Massive 5-minute aggregates. Data freshness is checked independently of subscription; 15-minute-delayed plans do not qualify for timely automatic entries.')
    else:
        st.warning('Unofficial Yahoo market data in use. This is not a professional live scanner. The simulation may skip entries or miss prices.')
    latest_ages = [round((now-v.get('last_observed_at')).total_seconds()/60,1) for v in summaries.values() if v.get('last_observed_at') is not None]
    if latest_ages:
        newest=min(latest_ages)
        st.caption(f'Newest available candle START is approximately {newest:g} minutes old. In live-like paper mode, a completed 5-minute bar must be available within 7 minutes of its END.')
        if newest>12 and status=='Regular session':
            st.warning('Market observations appear delayed or stale. The simulator will not open new virtual positions using old candles.')
    st.markdown('#### Today’s automatic watchlist')
    if symbols:
        st.write(', '.join('`'+x+'`' for x in symbols))
        st.caption('Chosen using observed premarket bars and measurable book-based filters. News and spreads are not automatically verified; these are not stock recommendations.')
    else:
        st.info('No eligible premarket shortlist saved for today. Simulation does nothing until qualifying current-day data appears. It does not invent a trade.')
    if state['positions']:
        st.markdown('#### Open virtual positions')
        rows=[]
        for symbol,p in state['positions'].items():
            rows.append(dict(Stock=symbol,Virtual_shares=p['qty'],Synthetic_entry=p['entry'],
                             Model_stop=p['stop'],Model_target=p['target'],Latest_observed=marks.get(symbol)))
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    else:
        st.caption('No virtual position currently open.')
    if state['pending']:
        st.info('Pending next-candle simulated entries: '+', '.join(state['pending']))
    m1,m2,m3=st.columns(3)
    m1.metric('Realized virtual P/L',f'${s["realized_pnl"]:+,.2f}')
    m2.metric('Closed-trade drawdown',f'{s["max_closed_equity_drawdown_pct"]:.2f}%')
    m3.metric('Trades to evaluate', max(0,30-s['closed_trades']))
    st.markdown('#### Virtual account progress')
    closed=sorted(state['closed_trades'],key=lambda x:x['exit_at'])
    if closed:
        values=[]; balance=state['starting_balance']
        for x in closed:
            balance += x['pnl']
            values.append({'Time':pd.Timestamp(x['exit_at']), 'Realized-only virtual equity':balance})
        st.line_chart(pd.DataFrame(values).set_index('Time'))
        st.dataframe(pd.DataFrame(closed[::-1]),use_container_width=True,hide_index=True)
        # Simple MIC flash-calendar-inspired practice record. No projected P/L.
        daily = pd.DataFrame(closed)
        dates = pd.to_datetime(daily['exit_at'], errors='coerce', utc=True)
        daily['Date (ET)'] = dates.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
        by_day = (daily.dropna(subset=['Date (ET)']).groupby('Date (ET)')
                   .agg(**{'Virtual P/L ($)':('pnl','sum'), 'Completed simulations':('pnl','size')})
                   .reset_index().sort_values('Date (ET)',ascending=False))
        with st.expander('📅 Paper practice calendar — daily closed-trade results'):
            st.dataframe(by_day,hide_index=True,use_container_width=True)
            st.caption('Inspired by the dated MIC trade-review calendar. Days without completed simulations do not imply any gain or loss. Older workbook calendar dates are not copied.')
        st.caption('Performance shown is after modeled slippage but before taxes, financing, realistic spread/commissions and feed latency; this is NOT a validated backtest.')
    with st.expander('Recent automatic decisions and diagnostics'):
        logs=state.get('events',[])[-30:][::-1]
        if logs:
            st.dataframe(pd.DataFrame(logs),hide_index=True,use_container_width=True)
        else:
            st.write('No simulated activity recorded yet.')
        st.write('When configured, both scanning and 5-minute bars use Massive; otherwise unofficial Yahoo. Delayed and stale bars suppress new entries. The page refreshes roughly every 5 minutes when open. GitHub Actions is an optional, imperfect unattended schedule.')
    st.download_button('Export paper account backup (JSON)',export_state(state),file_name='marketlens_paper_account_backup.json',mime='application/json')
    st.download_button('Export completed virtual trades (CSV)',pd.DataFrame(closed).to_csv(index=False),file_name='marketlens_virtual_trades.csv',mime='text/csv')
    st.divider()
    with st.expander('Advanced risk assumptions'):
        st.caption('These are virtual safeguards, not guaranteed limits. All order prices are synthetic.')
        st.json(state['settings'])
