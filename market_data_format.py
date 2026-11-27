"""Pure, tested Massive bar conversion (no API or Streamlit dependency)."""
from __future__ import annotations
import pandas as pd
from analytics import ET, tidy_ohlcv

def parse_aggregate_rows(rows: list[dict]) -> pd.DataFrame:
    """Convert provider's UTC millisecond bar START timestamps to exchange-local time."""
    if not rows:
        return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
    df = pd.DataFrame(rows)
    fields = {'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close', 'v': 'Volume'}
    if any(key not in df for key in ['t', *fields]):
        raise ValueError('Incomplete Massive OHLCV fields')
    df = df.rename(columns=fields)
    df.index = pd.to_datetime(df['t'], unit='ms', utc=True).dt.tz_convert(ET)
    return tidy_ohlcv(df[['Open', 'High', 'Low', 'Close', 'Volume']])

