from datetime import datetime,date,time,timedelta
from zoneinfo import ZoneInfo
import pandas as pd
from auto_simulator import advance_account, stats, equity, replay_one_day
from auto_store import new_account, get_engine, save_state, load_state
ET=ZoneInfo('America/New_York')

def bars_from_930(rows, day=date(2026,11,23)):
    idx=pd.date_range(datetime.combine(day,time(9,30),ET),periods=len(rows),freq='5min')
    return pd.DataFrame(rows,index=idx,columns=['Open','High','Low','Close','Volume'])


def bullish_stub(data,now,regular_session_open=True):
    # Current row was completed at the tested clock (9:40) without looking ahead.
    if now.time() == time(9,40):
        return dict(label='PAPER BUY CANDIDATE',data_valid=True,bar_end=now,
                    price=101,range_low=99,vwap=100)
    return dict(label='WAIT / REVIEW',data_valid=True,bar_end=now,price=100)


def starting():
    s=new_account(10000,datetime(2026,11,23,9,29,tzinfo=ET))
    s['activated_at']=datetime(2026,11,23,9,29,tzinfo=ET).isoformat()
    s['enabled']=True
    s['watch_by_day']={'2026-11-23':['TEST']}
    return s


def test_automatic_order_only_next_bar_and_unique():
    df=bars_from_930([[100,101,99,100,1000],[100,102,100,101,2000],[102,104,101,103,2500]])
    s=starting()
    advance_account(s,{'TEST':df},datetime(2026,11,23,9,40,tzinfo=ET),bullish_stub)
    assert s['cash']==10000 and not s['positions']
    assert s['pending']['TEST']['signal_end'].endswith('09:40:00-05:00')
    advance_account(s,{'TEST':df},datetime(2026,11,23,9,45,tzinfo=ET),bullish_stub)
    assert s['positions']['TEST']['entry']>102
    assert s['positions']['TEST']['qty']<=9  # max ~10% virtual notional
    n=len(s['events'])
    advance_account(s,{'TEST':df},datetime(2026,11,23,9,45,tzinfo=ET),bullish_stub)
    assert len(s['events'])==n


def test_intrabar_stop_priority_and_no_future_bars():
    df=bars_from_930([[100,101,99,100,1000],[100,102,100,101,2000],
                       [102,120,98,103,2500]])
    s=starting()
    advance_account(s,{'TEST':df},datetime(2026,11,23,9,45,tzinfo=ET),bullish_stub)
    assert not s['positions']
    assert len(s['closed_trades'])==1
    assert s['closed_trades'][0]['exit_reason']=='Entry candle stop'
    assert s['closed_trades'][0]['pnl']<0


def test_stale_auto_cannot_open_old_virtual_orders():
    df=bars_from_930([[100,101,99,100,1000],[100,102,100,101,2000],[102,105,101,103,2000]])
    s=starting()
    advance_account(s,{'TEST':df},datetime(2026,11,23,10,15,tzinfo=ET),bullish_stub)
    assert not s['pending'] and not s['positions'] and not s['closed_trades']


def test_local_database_roundtrip(tmp_path,monkeypatch):
    monkeypatch.setenv('MARKETLENS_DATABASE_URL','sqlite:///'+str(tmp_path/'account.db'))
    e=get_engine()
    s=starting();s['cash']=9850.50
    save_state(e,s)
    assert load_state(e)['cash']==9850.5


def test_historical_replay_is_separate_state():
    df=bars_from_930([[100,101,99,100,1000],[100,102,100,101,2000],[102,105,101,103,2500]])
    s=replay_one_day(df,'TEST',date(2026,11,23),signal_fn=bullish_stub)
    assert len(s['positions'])==1
    assert s['positions']['TEST']['entry']>102
    assert stats(s)['closed_trades']==0
