"""Deterministic, book-inspired paper simulation (never communicates with a broker).

All fills are synthetic. Signals use only bars completed by a particular time; a
signal can enter no earlier than the next candle's OPEN, with a slippage penalty.
Stops win ties against targets. A missing or delayed candle suppresses entries.
"""
from __future__ import annotations
from datetime import datetime, date, time, timedelta
from math import floor

# Live-like paper entries require nearly current completed data.
# Fifteen-minute-delayed feeds are for replay, not synthetic retroactive fills.
MAX_LIVE_BAR_AGE_SECONDS = 420
from zoneinfo import ZoneInfo
import pandas as pd
from analytics import as_et, tidy_ohlcv
from paper_signals import paper_signal, SIGNAL_BUY

ET = ZoneInfo('America/New_York')


def event(s, kind, at, ticker='', detail=''):
    s['events'].append(dict(time=at.isoformat(), type=kind, ticker=ticker, detail=detail))
    s['events'] = s['events'][-500:]


def equity(s, prices=None):
    prices = prices or {}
    return round(float(s['cash']) + sum(float(v['qty']) * float(prices.get(k, v['entry'])) for k, v in s['positions'].items()), 2)


def completed_trades(s):
    return len(s.get('closed_trades', []))


def stats(s):
    trades = s['closed_trades']
    realized = [float(t['pnl']) for t in trades]
    wins = [x for x in realized if x > 0]
    losses = [x for x in realized if x < 0]
    cum = s['starting_balance']
    peak = cum
    mdd = 0
    for t in sorted(trades, key=lambda x:x['exit_at']):
        cum += float(t['pnl'])
        peak = max(peak, cum)
        mdd = max(mdd, (peak-cum)/peak if peak else 0)
    return dict(closed_trades=len(trades), win_rate=(len(wins)/len(trades)*100 if trades else None),
                realized_pnl=round(sum(realized), 2), max_closed_equity_drawdown_pct=round(mdd*100, 2),
                avg_win=(sum(wins)/len(wins) if wins else None), avg_loss=(sum(losses)/len(losses) if losses else None),
                gross_profit=sum(wins), gross_loss=sum(losses))


def _size(s, entry, stop):
    if entry <= 0 or stop <= 0 or stop >= entry:
        return 0
    eq = equity(s)
    risk = eq * s['settings']['risk_percent'] / 100
    exposure = eq * s['settings']['exposure_percent'] / 100
    cash_available = float(s['cash'])
    return max(0, min(floor(risk/(entry-stop)), floor(exposure/entry), floor(cash_available/entry)))


def _settle(s, symbol, raw_price, bar_end, reason):
    pos = s['positions'].pop(symbol)
    slippage = s['settings']['slippage_bps']/10000
    price = round(max(.01, float(raw_price)*(1-slippage)), 4)
    fee = float(s['settings']['fee_per_side'])
    s['cash'] += pos['qty']*price-fee
    pnl = (price-pos['entry'])*pos['qty'] - pos['entry_fee'] - fee
    s['closed_trades'].append(dict(symbol=symbol, entry_at=pos['entered_at'], exit_at=bar_end.isoformat(),
                                   shares=pos['qty'], entry=pos['entry'], exit=price,
                                   stop=pos['stop'], target=pos['target'], pnl=round(pnl, 2),
                                   exit_reason=reason, strategy='5m ORB / VWAP / EMA'))
    event(s, 'PAPER CLOSE', bar_end, symbol, f'{reason}: synthetic price ${price:.2f}, P/L ${pnl:.2f}')


def _today_count(s, day):
    return sum(t['entry_at'][:10] == day for t in s['closed_trades']) + sum(p['entered_at'][:10]==day for p in s['positions'].values())


def _symbol_traded_today(s, symbol, day):
    return symbol in s['positions'] or any(t['symbol']==symbol and t['entry_at'][:10]==day for t in s['closed_trades'])


def _daily_loss_exceeded(s, day):
    daily_pnl = sum(float(t['pnl']) for t in s['closed_trades'] if t['exit_at'][:10]==day)
    return daily_pnl <= -s['starting_balance']*s['settings']['max_daily_loss_percent']/100


def select_research_watch(summaries, day, max_symbols=3, now=None):
    """Discover from user/Yahoo universe, but ONLY prior-session + observed PM bars.

    Book screening simplified: nonstale premarket gap and measurable liquidity.
    Does not imply complete market-wide scanning or validated news catalysts.
    """
    from morning_brief import morning_candidate
    cutoff = min((now or datetime.combine(day, time(9, 29), ET)).astimezone(ET), datetime.combine(day, time(9, 29), ET))
    eligible = []
    for symbol, summary in summaries.items():
        x = morning_candidate(symbol, summary, cutoff, 'Premarket')
        if x['rank'] >= 0 and x['label'] in ('Priority watch','Early watch'):
            eligible.append(x)
    return [r['ticker'] for r in sorted(eligible, key=lambda r:-r['rank'])[:max_symbols]]


def advance_account(state: dict, bars_by_symbol: dict, now: datetime, check_signal=paper_signal):
    """Advance an ALREADY ACTIVATED account using only completed 5m bars.

    Never invent fills in a future uncompleted bar. Missing past bars and stale
    signals are not new entries. The first allowed bar must END after activation.
    """
    now = now.astimezone(ET)
    if not state.get('enabled') or not state.get('activated_at'):
        return state
    activated = datetime.fromisoformat(state['activated_at']).astimezone(ET)
    if now.date() < activated.date():
        return state
    today_str = now.date().isoformat()
    watch = set(state.get('watch_by_day',{}).get(today_str, []))
    symbols = watch | set(state['positions']) | set(state['pending'])
    candidates = []
    all_frames = {}
    for symbol in symbols:
        raw = bars_by_symbol.get(symbol)
        if raw is None or raw.empty:
            continue
        d = as_et(tidy_ohlcv(raw))
        all_frames[symbol]=d
        current = d.loc[(d.index.date==now.date()) & (d.index.time >=time(9,30)) & (d.index.time<time(16))]
        last_processed = state['last_processed'].get(symbol)
        for idx,bar in current.iterrows():
            end = idx.to_pydatetime() + timedelta(minutes=5)
            if end <= activated or end > now or (last_processed and end.isoformat() <= last_processed):
                continue
            candidates.append((end, symbol, idx, bar))
    # chronological processing across tickers; no account ordering by ticker alone
    candidates.sort(key=lambda x:(x[0],x[1]))
    for end,symbol,start,bar in candidates:
        day=end.date().isoformat()
        # Record gap in provider bars: no entry on a candle missing its predecessor.
        last_time = state['last_processed'].get(symbol)
        contiguous = not last_time or (end - datetime.fromisoformat(last_time)) <= timedelta(minutes=5, seconds=1)
        state['last_processed'][symbol] = end.isoformat()
        if symbol in state['positions']:
            pos = state['positions'][symbol]
            if pos['entered_at'][:10] != day:
                # In practice the day-end close should prevent this. No overnight simulation.
                _settle(state, symbol, float(bar['Open']), end, 'Next session forced close')
            else:
                op,lo,hi = float(bar['Open']),float(bar['Low']),float(bar['High'])
                if op <= pos['stop']:
                    _settle(state,symbol,op,end,'Stop gap at open')
                elif op >= pos['target']:
                    _settle(state,symbol,op,end,'Target gap at open')
                elif lo <= pos['stop']:
                    _settle(state,symbol,pos['stop'],end,'Stop touched; conservative if both touched')
                elif hi >= pos['target']:
                    _settle(state,symbol,pos['target'],end,'Target touched')
                elif start.time() >= time(15,55):
                    _settle(state,symbol,float(bar['Close']),end,'Session closing bar')
        # Pending entry generated only at the previous CLOSED candle. Fill at NEXT open.
        pending = state['pending'].pop(symbol, None)
        if pending and symbol not in state['positions']:
            signal_time = datetime.fromisoformat(pending['signal_end'])
            # Only execute on *immediate* next 5m bar and within 15m of NOW.
            if (start.to_pydatetime() == signal_time and (now-end).total_seconds() <= MAX_LIVE_BAR_AGE_SECONDS and
                    symbol in watch and time(9,40)<=start.time()<time(11,30) and contiguous and
                    not _daily_loss_exceeded(state,day) and not _symbol_traded_today(state,symbol,day) and _today_count(state,day)<state['settings']['max_trades_day'] and
                    len(state['positions']) < state['settings']['max_positions']):
                raw_entry=float(bar['Open'])
                slip=state['settings']['slippage_bps']/10000
                entry=round(raw_entry*(1+slip),4)
                stop=float(pending['stop'])
                count=_size(state,entry,stop)
                if count > 0 and (count*entry + state['settings']['fee_per_side'])<=state['cash']:
                    fee=state['settings']['fee_per_side']
                    state['cash'] -= count*entry+fee
                    state['positions'][symbol]=dict(qty=count,entry=entry,stop=stop,
                        target=round(entry+2*(entry-stop),4), entered_at=start.to_pydatetime().isoformat(),
                        entry_fee=fee)
                    event(state,'PAPER OPEN',end,symbol,f'{count} virtual shares @ ${entry:.2f} (modeled next open)')
                    # Simulate stop/target in the entry candle without exploiting future data.
                    if float(bar['Low'])<=stop:
                        _settle(state,symbol,stop,end,'Entry candle stop')
                    elif float(bar['High'])>=state['positions'][symbol]['target']:
                        _settle(state,symbol,state['positions'][symbol]['target'],end,'Entry candle target')
                    continue
                event(state,'SKIPPED',end,symbol,'Virtual budget/limits prevent entry')
        # Signals originate from a completed bar, not its opening price.
        if symbol not in watch or symbol in state['positions'] or symbol in state['pending']:
            continue
        if not time(9,40) <= end.time() <= time(11,25):
            continue
        if not contiguous or (now-end).total_seconds() > MAX_LIVE_BAR_AGE_SECONDS:
            continue
        if _symbol_traded_today(state,symbol,day) or _daily_loss_exceeded(state,day) or _today_count(state,day) >= state['settings']['max_trades_day']:
            continue
        history = all_frames[symbol].loc[all_frames[symbol].index <= start]
        signal = check_signal(history,end,regular_session_open=True)
        if signal['label'] != SIGNAL_BUY or not signal['data_valid']:
            continue
        if signal['bar_end'] is None or signal['bar_end'].isoformat() != end.isoformat():
            continue
        invalidation=[x for x in (signal.get('range_low'),signal.get('vwap')) if x is not None and x<float(signal['price'])]
        if not invalidation:
            continue
        stop=max(invalidation)
        if float(signal['price'])-stop < 0.01:
            continue
        state['pending'][symbol]=dict(signal_end=end.isoformat(), stop=float(stop))
        event(state,'SETUP',end,symbol,'Rule-confirmed 5m ORB signal; next-bar simulated entry pending')
    return state


def replay_one_day(history: pd.DataFrame, symbol: str, day: date, balance=10000.0,
                   signal_fn=paper_signal) -> dict:
    """Independent historical replay with clock stepped through completed bars.

    This is NOT live account performance. The symbol was chosen in hindsight and
    results depend on available bars, synthetic fills, and missing liquidity costs.
    """
    from auto_store import new_account
    d = as_et(tidy_ohlcv(history))
    fresh = d.loc[(d.index.date == day)&(d.index.time>=time(9,30))&(d.index.time<time(16))]
    state = new_account(balance, datetime.combine(day,time(9,29),ET))
    state['activated_at']=datetime.combine(day,time(9,29),ET).isoformat()
    state['enabled']=True
    state['watch_by_day'][day.isoformat()]=[symbol]
    # Run the clock forward in the precise order candles become known.
    for ts in fresh.index:
        simulated_now=ts.to_pydatetime()+timedelta(minutes=5)
        advance_account(state,{symbol:d.loc[d.index<=ts]},simulated_now,signal_fn)
    return state
