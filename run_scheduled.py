"""Optional unattended cloud runner, invoked from GitHub Actions on its schedule.

Only processes virtual positions; delays/missing data may cause skipped simulations.
The runner exits without doing anything outside regular NYSE sessions.
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timedelta, time
import pandas_market_calendars as mcal
import pandas as pd
from analytics import ET
from auto_store import get_engine, load_state, save_state, is_cloud_database
from auto_simulator import advance_account, select_research_watch, event
from data_source import discover_candidate_universe
from massive_data import fetch_many_preferred as fetch_many
from book_strategies import book_gapper_screen
from analytics import premarket_statistics, watch_priority
from market_scanner import discover_massive, massive_key


def scheduled_run(now=None):
    now=now or datetime.now(ET)
    if not is_cloud_database():
        raise RuntimeError('Scheduled runner requires MARKETLENS_DATABASE_URL for shared, persistent cloud state.')
    cal=mcal.get_calendar('NYSE')
    schedule=cal.schedule(start_date=now.date(),end_date=now.date())
    if schedule.empty:
        return 'Closed: not a trading day.'
    open_at=schedule.iloc[0]['market_open'].tz_convert(ET).to_pydatetime()
    close_at=schedule.iloc[0]['market_close'].tz_convert(ET).to_pydatetime()
    if not (time(9,0)<=now.time() and now <= close_at+timedelta(minutes=5)):
        return 'Outside paper-simulation schedule.'
    eng=get_engine()
    state=load_state(eng)
    if not state or not state.get('enabled'):
        return 'Paper simulation is not activated in the app.'
    day=now.date().isoformat()
    watch=state.get('watch_by_day',{}).get(day,[])
    symbols=list(dict.fromkeys(watch + list(state['positions']) + list(state['pending'])))
    if not watch and (time(9,0)<=now.time()<=time(9,35)):
        discovery=discover_massive(now) if massive_key() and now.time()<time(9,30) else discover_candidate_universe()
        candidates=discovery.get('symbols',[])
        candidates=list(dict.fromkeys(candidates+['SPY','QQQ','NVDA','AMD','TSLA','AAPL','META','AMZN','MSFT']))[:16]
        data=fetch_many(candidates)
        # Premarket-only observations as of actual now; never use future quote.
        summary={}
        for s, value in data.items():
            summary[s]=premarket_statistics(value['intraday'],value['daily'],now,is_trading_day=True)
            summary[s]['book_gapper']=book_gapper_screen(value['intraday'],value['daily'],now,is_trading_day=True)
        watch=select_research_watch(summary,now.date(),now=now)
        if watch:
            state['watch_by_day'][day]=watch
            event(state,'WATCHLIST',now,detail=', '.join(watch))
            save_state(eng,state)
            symbols=list(dict.fromkeys(watch+list(state['positions'])+list(state['pending'])))
    if not symbols:
        return 'No qualified premarket watchlist; no virtual trades.'
    data=fetch_many(symbols)
    if open_at <= now <= close_at+timedelta(minutes=5):
        before=len(state['events'])
        state=advance_account(state,{x:v['intraday'] for x,v in data.items()},now)
        if len(state['events'])!=before or state.get('last_processed'):
            save_state(eng,state)
    return f'Paper-only run: {len(symbols)} monitored; {len(state["positions"])} open; {len(state["closed_trades"])} completed.'


if __name__=='__main__':
    try:
        print(scheduled_run())
    except Exception as exc:
        print(f'Scheduled paper simulator failed: {exc}',file=sys.stderr)
        raise
