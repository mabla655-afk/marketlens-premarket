from datetime import date
import pandas as pd
import pytest
from mic_coach import (pivot_levels,previous_session,float_rotation,readable_context,
                       virtual_position_example,MIC_GLOSSARY,SOURCE_GUIDE)


def test_exact_mic_rock_pivot_spreadsheet():
    # @Modern_Rock Pivots.xlsx: H 7.47, L 6.61, C 7.25; cached formulas B11:B24.
    p=pivot_levels(7.47,6.61,7.25)
    expected={'P':7.11,'R1':7.61,'R2':7.97,'R3':8.47,'R4':8.97,'R5':9.47,
              'R6':9.97,'R7':10.47,'R8':10.97,'S1':6.75,'S2':6.25,
              'S3':5.89,'S4':5.53,'S5':5.17,'S6':4.81}
    for level, value in expected.items():
        assert p[level] == pytest.approx(value),level


def test_today_incomplete_candle_never_becomes_previous_day():
    dates=pd.DatetimeIndex(['2026-11-24','2026-11-25','2026-11-26'],tz='America/New_York')
    daily=pd.DataFrame({'High':[8.,7.47,99.], 'Low':[6.,6.61,0.1],
                        'Close':[7.,7.25,20.]},index=dates)
    prior=previous_session(daily,date(2026,11,26))
    assert prior['date']=='2026-11-25' and prior['close']==7.25


def test_no_daily_or_invalid_inputs_mean_no_pivots():
    assert previous_session(pd.DataFrame(),date(2026,11,26)) is None
    with pytest.raises(ValueError):
        pivot_levels(4,6,5)


def test_float_rotation_uses_verified_input_only():
    assert float_rotation(500000,1000000)==pytest.approx(.5)
    assert float_rotation(500000,None) is None
    assert float_rotation(300,-1) is None


def test_missing_fundamentals_are_not_assumed_good_or_bad():
    result=readable_context({'premarket_gap_pct':None,'premarket_volume':None},None,None)
    assert result['float_rotation'] is None
    assert len(result['cautions'])==0
    assert 'RESEARCH ONLY' in result['automation']
    assert 'not been verified' in ' '.join(result['observations'])


def test_mic_short_cautions_are_labeled_research_only():
    result=readable_context({'premarket_gap_pct':75,'premarket_volume':100_000},
                            float_shares=2_000_000,short_float_pct=22)
    assert len(result['cautions'])==3
    assert result['float_rotation']==pytest.approx(.05)
    assert 'RESEARCH ONLY' in result['automation']


def test_virtual_size_is_bounded_on_example_only():
    p=virtual_position_example(10000,10,9.8)
    assert p['virtual_shares']==100
    assert p['risk_at_stop']==pytest.approx(20)
    assert p['virtual_notional']==1000
    assert p['two_r_reference']==pytest.approx(10.4)
    assert virtual_position_example(10000,10,10.2) is None


def test_guide_has_human_readable_terms_and_sources():
    assert len(MIC_GLOSSARY)>=10
    assert len(SOURCE_GUIDE)>=7
