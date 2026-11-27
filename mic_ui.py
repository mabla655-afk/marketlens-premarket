"""Beginner-friendly MIC educational research tab (no broker/API order commands)."""
from __future__ import annotations
import json
import pandas as pd
import streamlit as st
from mic_coach import (MIC_GLOSSARY, SOURCE_GUIDE, pivot_levels, previous_session,
                       readable_context, virtual_position_example)


def _usd(value):
    return f'${value:,.2f}' if value is not None else 'Not available'


def show_mic_tab(now, results, summaries, symbols):
    st.header('🧭 MIC Coach — Understand the market')
    st.caption('Inspired by the MIC files you provided. All levels are research references. This tab does not open trades, short shares, or control your automatic paper simulator.')
    st.info('**Simple rule:** Price + volume tell us what has happened, not what will happen next. When news, float, spread or filings are missing, the app says **Not checked**.')
    with st.expander('📖 Explain the words on my screen', expanded=False):
        term=st.selectbox('Trading term',list(MIC_GLOSSARY),key='mic_glossary_term')
        st.write(MIC_GLOSSARY[term])
        st.caption('Definitions are original short educational explanations based on the MIC Starter Pack (2023), pp. 3–9 and 20–22.')

    ticker = st.selectbox('Stock to investigate', symbols, key='mic_ticker')
    info = summaries.get(ticker,{})
    data = results.get(ticker,{})
    st.markdown('### 1. What do we actually know?')
    a,b,c=st.columns(3)
    a.metric('Last observed price',_usd(info.get('last_observed_price')))
    gp=info.get('premarket_gap_pct')
    b.metric('Observed premarket gap',f'{gp:+.1f}%' if gp is not None else 'Not available')
    pmv=info.get('premarket_volume')
    c.metric('Premarket shares traded',f'{pmv:,.0f}' if pmv is not None else 'Not available')
    if info.get('last_observed_at') is not None:
        st.caption(f'Last observed price bar began: {info["last_observed_at"]:%b %d, %I:%M %p} ET. Verify the provider delay before interpreting it.')
    else:
        st.warning('No timestamped current observation available. Do not treat the displayed numbers as live.')

    with st.expander('Add facts from MIC Game Plan (optional)',expanded=True):
        st.caption('These are manual research fields. The app cannot verify company filings or short interest automatically with the basic price feed.')
        c1,c2=st.columns(2)
        with c1:
            float_m=st.number_input('Verified float (millions of shares; 0 = unknown)',min_value=0.0,value=0.0,step=0.5, key='mic_float_'+ticker)
            short_float=st.number_input('Reported short float % (0 = unknown)',min_value=0.0,max_value=100.0,value=0.0,step=1.0,key='mic_short_'+ticker)
        with c2:
            news=st.selectbox('News catalyst verified?', ['Not checked','Verified company announcement','Earnings announcement','No clear catalyst found'],key='mic_catalyst_'+ticker)
            filing=st.selectbox('Dilution / filing review', ['Not checked','Recent filing reviewed — possible dilution','Recent filings reviewed — no clear dilution noted'],key='mic_filing_'+ticker)
        context=readable_context(info,float_shares=float_m*1e6 if float_m>0 else None,
                                 short_float_pct=short_float if short_float>0 else None,
                                 catalyst=news, filing_status=filing)
    for text in context['observations']:
        st.write('• '+text)
    for text in context['cautions']:
        st.warning(text)
    st.caption('MIC Checklist.docx: bullish/bearish factors. These factors can conflict and are NOT a weighted probability score. 9:29 a.m. conditions, dilution and ownership need independent verification.')

    st.divider()
    st.markdown('### 2. Identify nearby chart reference levels')
    prior=previous_session(data.get('daily',pd.DataFrame()),now.date())
    if prior:
        st.caption(f'Prior completed trading day: {prior["date"]}. Source: {data.get("source","Provider not identified")}. Values must be unadjusted and from the same session.')
        p=pivot_levels(prior['high'],prior['low'],prior['close'])
        x,y,z=st.columns(3)
        x.metric('Yesterday high',_usd(prior['high']))
        y.metric('Yesterday low',_usd(prior['low']))
        z.metric('Yesterday close',_usd(prior['close']))
        st.metric('MIC Rock pivot (P)',_usd(p['P']))
        levels=[('Resistance 3',p['R3']),('Resistance 2',p['R2']),('Resistance 1',p['R1']),
                ('Pivot',p['P']),('Support 1',p['S1']),('Support 2',p['S2']),('Support 3',p['S3'])]
        with st.expander('Show MIC pivot and support/resistance levels',expanded=True):
            st.dataframe(pd.DataFrame([{'Chart reference':k,'Price ($)':round(v,4)} for k,v in levels]),hide_index=True,use_container_width=True)
            st.caption('Calculated from your @Modern_Rock Pivots.xlsx formulas. Levels are not automatically buy, sell, stop, or target instructions.')
    else:
        st.warning('No complete prior-day high/low/close in the current feed. Pivot calculations have been withheld rather than guessed.')

    st.divider()
    st.markdown('### 3. Build a simple educational game plan')
    st.caption('From MIC Game-Plan.docx and Checklist.docx. Your notes can be downloaded but are not automatically stored in the cloud database.')
    big_picture=st.text_area('Big picture — what is happening in the overall market?',key='mic_picture_'+ticker,height=70,
                             placeholder='Example: Is the overall index moving steadily or unpredictably?')
    reason=st.text_area('Why is this stock moving? What source did you verify?',key='mic_reason_'+ticker,height=70,
                        placeholder='Example: Earnings announcement on the company website, or not verified')
    levels=st.text_area('Which areas might matter, and why?',key='mic_levels_'+ticker,height=70,
                        placeholder='Example: Prior high, VWAP, opening range; note that a level can fail')
    skip=st.text_area('What would make this a NO-TRADE practice day?',key='mic_skip_'+ticker,height=70,
                      placeholder='Example: Outdated data, no clear setup, wide spread, unverified catalyst')
    plan=dict(ticker=ticker,date=now.date().isoformat(),source='MIC educational worksheet',
              observed_price=info.get('last_observed_price'),previous_session=prior,
              float_millions=float_m or None, short_float_percent=short_float or None,
              catalyst_review=news, filing_review=filing,big_picture=big_picture,
              research_reason=reason, key_levels=levels, why_skip=skip)
    st.download_button('Download my MIC research note',json.dumps(plan,indent=2,default=str),
                       file_name=f'mic_research_{ticker}_{now:%Y%m%d}.json',mime='application/json')
    st.caption('For repeat use, verify your sources each morning. Do not copy qualitative fields forward as if they were still current.')

    st.divider()
    st.markdown('### 4. Understand a virtual position-size example')
    st.caption('This calculator is separate from the automatic simulator and cannot create a paper or real order. It is based on the principle illustrated in MIC Pos. Calc.xlsx.')
    ca,cb,cc=st.columns(3)
    virtual_balance=ca.number_input('Virtual balance ($)',1000.0,100000.0,10000.0,1000.0,key='mic_practice_balance')
    example_entry=cb.number_input('Example entry reference ($)',0.01,10000.0,10.0,0.1,key='mic_practice_entry')
    example_stop=cc.number_input('Example invalidation reference ($)',0.01,10000.0,9.80,0.1,key='mic_practice_stop')
    calc=virtual_position_example(virtual_balance,example_entry,example_stop)
    if calc:
        xa,xb,xc=st.columns(3)
        xa.metric('Virtual shares',str(calc['virtual_shares']))
        xb.metric('Illustrative maximum loss at level',_usd(calc['risk_at_stop']))
        xc.metric('Illustrative 2R reference',_usd(calc['two_r_reference']))
        st.caption(f'Example settings: 0.5% virtual risk and 10% maximum virtual exposure. Max virtual position value { _usd(calc["exposure_cap"]) }. Assumes exact reference fills; actual spreads, gaps and price movement could differ.')
    else:
        st.info('Enter a reference entry higher than the invalidation level to see the long-only arithmetic example.')

    with st.expander('How the MIC handouts are used — and what is not automated'):
        for source,description in SOURCE_GUIDE:
            st.markdown('**'+source+'** — '+description)
        st.warning('MIC concentrates on some discretionary and short-side techniques. This app keeps these as education and cautions, not automatic short entries. Existing automated paper strategy remains the tested-in-code simplified BBT long-only 5-minute ORB, not an MIC strategy. No DAS command files are run or re-created.')
