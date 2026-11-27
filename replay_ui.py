"""Streamlit Market Replay tab. No calls to persistent paper-account writes."""
from __future__ import annotations
from datetime import timedelta
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from analytics import ET
from replay_coach import regular_bars_for_day, replay_dates, replay_snapshot, classify_next_close
from massive_data import fetch_history_preferred


def _replay_chart(snapshot):
    visible=snapshot['visible']
    fig=go.Figure()
    fig.add_trace(go.Candlestick(x=visible.index,open=visible['Open'],high=visible['High'],
                                 low=visible['Low'],close=visible['Close'],name='Candles revealed',
                                 increasing_line_color='#2dd4bf',decreasing_line_color='#fb7185'))
    bounds=snapshot['bounds']
    if bounds['high'] is not None:
        fig.add_hline(y=bounds['high'],line_dash='dash',line_color='#2dd4bf',annotation_text='Opening high')
        fig.add_hline(y=bounds['low'],line_dash='dash',line_color='#fb7185',annotation_text='Opening low')
    p=list(snapshot['engine']['positions'].values())
    if p:
        fig.add_hline(y=p[0]['entry'],line_dash='dot',line_color='#fff',annotation_text='Simulated entry')
        fig.add_hline(y=p[0]['stop'],line_dash='dot',line_color='#fb7185',annotation_text='Virtual stop')
        fig.add_hline(y=p[0]['target'],line_dash='dot',line_color='#2dd4bf',annotation_text='Virtual target')
    fig.update_layout(template='plotly_dark',height=435,margin=dict(t=15,b=10,l=5,r=5),
                      xaxis_title='Eastern Time — revealed candles only',yaxis_title='Price ($)',
                      xaxis_rangeslider_visible=False,showlegend=False)
    return fig


def _reset_step():
    st.session_state['_market_replay_step']=1


def _step_delta(delta, cap):
    st.session_state['_market_replay_step']=max(1,min(cap,st.session_state.get('_market_replay_step',1)+delta))


def show_replay_tab(default_symbols):
    st.subheader('🎞️ Market Replay — learn one candle at a time')
    st.write('Practice understanding an actual **past** market session without seeing candles that have not yet been revealed. No real orders. Replay results are **not** added to your saved paper account.')
    st.caption('Educational ORB walkthrough: one completed 5-minute candle at a time · simplified BBT-based long-only virtual logic · observed history, not a forecast')
    symbols=list(dict.fromkeys(default_symbols))
    if not symbols:
        st.info('Add a ticker to your watchlist first, then return to Replay.')
        return
    c1,c2=st.columns([2,1])
    with c1:
        chosen=st.selectbox('Choose stock for historical practice',symbols,key='_replay_symbol')
    with c2:
        load=st.button('Load historical sessions',type='primary',use_container_width=True)
    if load:
        with st.spinner('Loading historical five-minute candles from your configured provider...'):
            fetched=fetch_history_preferred(chosen)
        if fetched.get('bars') is None or fetched['bars'].empty:
            st.session_state['_market_replay_source']=None
            st.error('No replay history available: '+str(fetched.get('error') or 'Provider returned no usable bars.'))
        else:
            st.session_state['_market_replay_source']={'symbol':chosen,'bars':fetched['bars']}
            _reset_step()
    cached=st.session_state.get('_market_replay_source')
    if not cached or cached['symbol']!=chosen:
        st.info('Click **Load historical sessions** to start a replay for this ticker.')
        return
    from datetime import datetime
    options=replay_dates(cached['bars'],datetime.now(ET).date())
    if not options:
        st.warning('No previous session with complete opening candles found. Your provider may restrict intraday history.')
        return
    choice=st.selectbox('Choose a completed historical session',options,format_func=lambda d:d.strftime('%a, %b %d, %Y'),
                        key='_replay_day',on_change=_reset_step)
    session=regular_bars_for_day(cached['bars'],choice)
    count=len(session)
    if count < 3:
        st.info('Too few complete five-minute candles for a meaningful replay.')
        return
    if '_market_replay_step' not in st.session_state:
        st.session_state['_market_replay_step']=1
    st.session_state['_market_replay_step']=min(st.session_state['_market_replay_step'],count)
    btnprev,btnnext,btnend=st.columns([1,1,1])
    with btnprev:
        st.button('◀ Previous candle',on_click=_step_delta,args=(-1,count),disabled=st.session_state['_market_replay_step']<=1,use_container_width=True)
    with btnnext:
        st.button('Reveal next candle ▶',on_click=_step_delta,args=(1,count),disabled=st.session_state['_market_replay_step']>=count,use_container_width=True,type='primary')
    with btnend:
        st.button('Restart from 9:30',on_click=_reset_step,use_container_width=True)
    st.slider('Candles revealed',min_value=1,max_value=count,key='_market_replay_step',
              help='Move forward or backward through history. The app never shows later candles until you reveal them.')
    try:
        snap=replay_snapshot(cached['bars'],chosen,choice,st.session_state['_market_replay_step'])
    except (ValueError,KeyError,TypeError) as exc:
        st.error('Cannot replay this session: '+str(exc))
        return
    st.progress(snap['revealed']/snap['total'])
    st.caption(f"Practice clock: **{snap['asof']:%I:%M %p} ET** · {snap['revealed']} / {snap['total']} completed candles · the remaining candles are hidden")
    a,b=st.columns([1.8,1])
    with a:
        st.plotly_chart(_replay_chart(snap),use_container_width=True)
    with b:
        st.markdown('### What this candle means')
        st.info('**'+snap['title']+'**\n\n'+snap['explanation'])
        st.markdown('**What to look at next**')
        st.write(snap['next_step'])
        last=snap['visible'].iloc[-1]
        st.metric('Last revealed close',f"${last['Close']:.2f}")
        st.metric('Shares traded in this 5-min candle',f"{last['Volume']:,.0f}")
        st.caption('Volume is the observed number of shares traded during this candle; it is NOT a suggested number of shares to buy.')
    st.markdown('#### Why did the strategy pass or wait?')
    checks=snap['signal'].get('checks',{})
    if checks:
        for label,value in checks.items():
            mark='✅' if value is True else ('❌' if value is False else '❔')
            st.markdown(f'{mark} {label}')
    else:
        st.caption('The strategy does not yet have enough completed observations for reliable checks. '+snap['signal'].get('reason',''))
    st.markdown('#### Quick practice: what might the next candle do?')
    st.caption('You can make a guess, then reveal the next candle. This is a learning exercise, not a prediction or trade instruction.')
    guesses=st.session_state.setdefault('_replay_guesses',{})
    if snap['revealed']>1:
        prev_key=f"{chosen}:{choice}:{snap['revealed']-1}"
        if prev_key in guesses:
            earlier=float(snap['visible'].iloc[-2]['Close'])
            current=float(snap['visible'].iloc[-1]['Close'])
            actual=classify_next_close(earlier,current)
            guessed=guesses[prev_key]
            st.info(f"Previous guess: **{guessed}** · Observed next close: **{actual}**. "
                    "One candle does not establish whether a method predicts the market.")
    if not snap['done']:
        next_key=f"{chosen}:{choice}:{snap['revealed']}"
        if next_key not in guesses:
            with st.form(f'_guess_form_{chosen}_{choice}_{snap["revealed"]}'):
                guess=st.radio('Compared with this close, where will the next candle finish?',
                               ['Higher','Lower','About the same'],horizontal=True)
                if st.form_submit_button('Save my guess'):
                    guesses[next_key]=guess
                    st.success('Guess saved. Now click **Reveal next candle** to see what happened.')
        else:
            st.caption('Your guess is saved. Reveal the next candle when you are ready.')
    if snap['engine'].get('pending'):
        st.warning('A hypothetical signal is pending a next-candle entry. No fill is assumed before the next candle opens.')
    if snap['engine'].get('positions'):
        st.caption('An illustrative long-only paper position is open. Prices and shares are synthetic; there is no brokerage order.')
    with st.expander('Show the virtual trade event log',expanded=bool(snap['closed'])):
        events=snap['engine'].get('events',[])
        if events:
            st.dataframe(pd.DataFrame(events),hide_index=True,use_container_width=True)
        else:
            st.caption('No simulated order events yet.')
    if snap['done']:
        st.success('End of the available historical candles for this date. Some data providers may return partial sessions.')
        st.write(f"**Historical virtual results:** {snap['metrics']['closed_trades']} closed trade(s), "
                 f"${snap['metrics']['realized_pnl']:+,.2f} modeled realized P/L.")
        if snap['engine'].get('positions'):
            st.warning('A position remained open because the provider did not supply the last session candle. This is not a complete end-of-day result.')
        st.caption('The ticker and date were selected retrospectively, creating hindsight/selection bias. Synthetic fills omit full execution, liquidity and all potential fees. Past results do not predict future outcomes.')
    else:
        st.caption('Results from the remaining candles are hidden until you reveal them. Choosing a stock/date afterward still introduces hindsight bias.')
    with st.expander('Plain-English chart glossary'):
        st.markdown('**Candle:** five minutes of observed prices. **Opening high/low:** the first 9:30–9:35 candle boundaries. **VWAP:** average price weighted by shares traded. **Volume:** shares traded, *not* virtual order size. **Stop/target:** modeled study levels, not guaranteed transaction prices. **Relative volume:** current candle volume compared with the same time on prior sessions, when sufficient history exists.')
