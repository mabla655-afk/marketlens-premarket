from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from morning_brief import simulation_plan, freshness_gate, morning_candidate, simulate_exit_watch

ET = ZoneInfo('America/New_York')


def test_paper_allocation_risk_exposure_caps():
    plan = simulation_plan(100, 98, 10_000, 0.5, 10)
    assert plan is not None
    assert plan.shares == 10  # $1000 exposure cap, despite $50 risk allowance
    assert plan.virtual_notional == 1000
    assert plan.virtual_risk_at_level == 20
    assert plan.target_2r == 104


def test_paper_cannot_size_wrong_side_or_infinite_or_overleveraged():
    assert simulation_plan(10, 11) is None
    assert simulation_plan(float('nan'), 9) is None
    assert simulation_plan(10, 9, 1000, 0.5, 0) is None
    assert simulation_plan(10_000, 9990, 1000, 0.5, 10).shares == 0


def test_no_stale_premarket_picks():
    now = datetime(2026, 11, 23, 8, 45, tzinfo=ET)
    summary = {'premarket_observed_at': now - timedelta(minutes=35),
               'premarket_gap_pct': 4.1, 'premarket_volume': 200000}
    assert not freshness_gate(summary['premarket_observed_at'], now)
    result = morning_candidate('TEST', summary, now, 'Premarket')
    assert result['rank'] == -1
    assert result['label'] == 'No current premarket data'
    assert morning_candidate('TEST', summary, now, 'Regular session')['rank'] == -1


def test_book_screen_translated_to_watch_not_buy():
    now = datetime(2026, 11, 23, 9, 10, tzinfo=ET)
    summary = {'premarket_observed_at': now-timedelta(minutes=5),
               'premarket_gap_pct': 6, 'premarket_volume': 190000,
               'book_gapper': {'checks': {'Gap magnitude ≥ 2%': True,
                           'PM volume ≥ 100K by 9:00 ET': True,
                           '20-day average volume > 500K': True,
                           '14-day ATR ≥ $0.50': True}}}
    result = morning_candidate('TEST', summary, now, 'Premarket')
    assert result['label'] == 'Priority watch'
    assert 'NOT verified' in result['note']


def test_exit_watch_freshness():
    held = {'qty': 5, 'reference_entry': 100, 'target_2r': 104, 'invalidation_reference': 98}
    assert 'unavailable' in simulate_exit_watch(held, {'data_valid': False}).lower()
    assert 'below session VWAP' in simulate_exit_watch(held, {'data_valid': True, 'price': 99, 'vwap': 100})
    assert '2R' in simulate_exit_watch(held, {'data_valid': True, 'price': 104, 'vwap': 101})
