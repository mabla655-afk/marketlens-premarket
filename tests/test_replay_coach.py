"""No-lookahead, stable teaching explanations, and account independence."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
import pandas as pd
import pytest
from replay_coach import regular_bars_for_day, replay_dates, replay_snapshot
ET=ZoneInfo('America/New_York')
DAY=date(2026,11,23)


def sample():
    frames=[]
    for day in ['2026-11-17','2026-11-18','2026-11-19','2026-11-20','2026-11-23']:
        idx=pd.date_range(f'{day} 09:30',periods=24 if day != '2026-11-23' else 12, freq='5min',tz=ET)
        rows=[]
        for i in range(len(idx)):
            p=101+0.05*i
            if day=='2026-11-23':
                p=103 + 0.08*i
            rows.append([p,p+0.2,p-0.2,p,1500 if i != 2 else 5000])
        frames.append(pd.DataFrame(rows,index=idx,columns=['Open','High','Low','Close','Volume']))
    return pd.concat(frames)


def test_replay_never_sees_future_prices():
    full=sample()
    early=replay_snapshot(full,'TEST',DAY,2)
    cut=full.loc[full.index<=pd.Timestamp('2026-11-23 09:35',tz=ET)]
    x=replay_snapshot(cut,'TEST',DAY,2)
    assert early['visible'].equals(x['visible'])
    assert early['title']==x['title']
    assert early['engine']==x['engine']
    assert len(early['visible'])==2
    assert early['asof'].time().strftime('%H:%M')=='09:40'
    assert early['metrics']['closed_trades']==0


def test_second_candle_explains_boundaries():
    s=replay_snapshot(sample(),'TEST',DAY,2)
    assert s['title']=='Opening range established'
    assert s['bounds']['high'] is not None
    assert s['bounds']['low'] is not None
    assert 'not forecasts' in s['explanation']


def test_replay_dates_exclude_current_and_poor_sessions():
    full=sample()
    days=replay_dates(full,date(2026,11,24))
    assert days[0]==DAY
    assert date(2026,11,24) not in days
    assert replay_dates(full,date(2026,11,23))[0]==date(2026,11,20)


def test_replay_result_is_independent_of_neon(monkeypatch):
    import auto_store
    def unavailable(*args,**kwargs):
        raise AssertionError('Replay must not open database connections')
    monkeypatch.setattr(auto_store,'get_engine',unavailable)
    s=replay_snapshot(sample(),'TEST',DAY,5)
    assert 'engine' in s
    assert 'metrics' in s


def test_no_replay_without_opening_candle():
    full=sample().loc[lambda x: ~((x.index.date==DAY)&(x.index.strftime('%H:%M')=='09:30'))]
    with pytest.raises(ValueError,match='opening'):
        replay_snapshot(full,'TEST',DAY,2)


def test_end_of_day_result_only_when_all_candles_revealed():
    full=sample()
    a=replay_snapshot(full,'TEST',DAY,1)
    z=replay_snapshot(full,'TEST',DAY,12)
    assert not a['done'] and z['done']
    assert z['revealed']==12


def test_quiz_direction_uses_only_revealed_closes():
    from replay_coach import classify_next_close
    assert classify_next_close(100,100.30)=='Higher'
    assert classify_next_close(100,99.80)=='Lower'
    assert classify_next_close(100,100.03)=='About the same'
