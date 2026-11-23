from datetime import date, datetime
import pandas as pd
import numpy as np
from zoneinfo import ZoneInfo
from book_strategies import atr14, avg_daily_volume, book_gapper_screen, anchored_vwap, orb_marks, orb_history, STRATEGY_LIBRARY

ET=ZoneInfo('America/New_York')


def daily():
    ts=pd.date_range('2026-09-01',periods=52,freq='B')
    c=100+np.arange(len(ts))*.1
    return pd.DataFrame({'Open':c,'High':c+1,'Low':c-1,'Close':c,'Volume':[600000]*len(ts)},index=ts)


def intraday_orb(day):
    idx=pd.date_range(f'{day} 09:30',periods=8,freq='5min',tz=ET)
    close=[10.5,10.8,11.2,11.1,11.5,11.7,12.0,12.1]
    highs=[11,11,11.4,11.3,11.7,11.9,12.2,12.2]
    lows=[10,10.4,10.7,10.9,11.1,11.3,11.8,12.0]
    return pd.DataFrame({'Open':close,'High':highs,'Low':lows,'Close':close,'Volume':[1000]*8},index=idx)


def test_source_rules_documented():
    assert len(STRATEGY_LIBRARY)>=10
    assert any('Opening Range' in x['name'] for x in STRATEGY_LIBRARY)


def test_atr_uses_prior_complete_sessions():
    d=daily(); x=atr14(d, date(2026,11,23)); assert x is not None and x>0
    d.loc[pd.Timestamp('2026-11-23'),['High','Low']]=[100000,1]
    assert atr14(d,date(2026,11,23))==x
    assert avg_daily_volume(d,date(2026,11,23))==600000


def test_no_book_gapper_screen_without_current_pm_data():
    x=book_gapper_screen(pd.DataFrame(),daily(),datetime(2026,11,23,8,0,tzinfo=ET),True)
    assert x['checks']['Gap magnitude ≥ 2%'] is None
    assert x['checks']['PM volume ≥ 100K by 9:00 ET'] is None
    assert not x['automated_pass']


def test_gapper_9am_volume_does_not_use_later_bars():
    idx=pd.date_range('2026-11-23 08:50',periods=6,freq='5min',tz=ET)
    d=pd.DataFrame({'Open':[120.]*6,'High':[121.]*6,'Low':[119.]*6,'Close':[120.]*6,
        'Volume':[60000,60000,900000,900000,900000,900000]},index=idx)
    x=book_gapper_screen(d,daily(),datetime(2026,11,23,9,20,tzinfo=ET),True)
    assert x['pm_volume_at_9']==120000
    assert x['checks']['PM volume ≥ 100K by 9:00 ET'] is True
    assert x['checks']['Verified news catalyst'] is None


def test_vwap_reset_by_session():
    x=intraday_orb('2026-11-19')
    y=intraday_orb('2026-11-20');y['Close']+=100;y['High']+=100;y['Low']+=100
    out=anchored_vwap(pd.concat([x,y]))
    assert out.loc[y.index[0]]>100
    assert out.loc[x.index[0]]<20


def test_orb_one_first_break_each_direction():
    d=intraday_orb('2026-11-20')
    o=orb_marks(d,date(2026,11,20))
    assert o['high']==11
    assert len(o['events'])==1
    assert o['events'][0]['at'].time().strftime('%H:%M')=='09:40'
    assert o['events'][0]['direction']=='Above range'


def test_missing_opening_candle_no_signal():
    d=intraday_orb('2026-11-20').iloc[1:]
    assert orb_marks(d,date(2026,11,20))['events']==[]


def test_orb_history_excludes_today_and_no_future_leakage():
    d=pd.concat([intraday_orb('2026-11-19'),intraday_orb('2026-11-20')])
    x=orb_history(d,date(2026,11,20),3)
    assert x['count']==1
    assert x['follow_through_pct']==100
    # With an artificial missing next bar, signal is skipped; no altered horizon.
    broken=intraday_orb('2026-11-19').drop(pd.Timestamp('2026-11-19 09:45',tz=ET))
    assert orb_history(broken,date(2026,11,20),3)['count']==0
