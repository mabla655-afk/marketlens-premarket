"""Synthetic contract tests for the new Massive OHLCV adapter."""
import pytest
from market_data_format import parse_aggregate_rows

def test_empty_rows():
    d=parse_aggregate_rows([])
    assert d.empty and list(d.columns)==['Open','High','Low','Close','Volume']

def test_timestamp_converted_from_utc_millis_to_market_timezone():
    # Nov 23 2026, 14:30 UTC = 09:30 ET (NYSE open).
    import datetime
    ms=int(datetime.datetime(2026,11,23,14,30,tzinfo=datetime.timezone.utc).timestamp()*1000)
    bars=parse_aggregate_rows([{'o':100,'h':101,'l':99,'c':100.5,'v':5000,'t':ms}])
    assert bars.index[0].hour==9 and bars.index[0].minute==30
    assert bars.index.tz is not None
    assert bars.iloc[0]['Volume']==5000

def test_reject_incomplete_bar_fields():
    with pytest.raises(ValueError):
        parse_aggregate_rows([{'t':123,'c':100}])
