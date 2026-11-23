"""Paper account storage. External PostgreSQL is REQUIRED for cloud durability.
Local SQLite is provided for experimentation only; not durable on Streamlit Cloud.
"""
from __future__ import annotations
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, text

ET = ZoneInfo('America/New_York')


def database_url() -> str:
    raw = os.environ.get('MARKETLENS_DATABASE_URL', '').strip()
    if not raw:
        try:
            import streamlit as st
            raw = str(st.secrets.get('MARKETLENS_DATABASE_URL', '')).strip()
        except Exception:
            pass
    if raw.startswith('postgres://'):
        raw = 'postgresql://' + raw[len('postgres://'):]
    if raw.startswith('postgresql://'):
        return 'postgresql+psycopg://' + raw[len('postgresql://'):]
    return raw if raw else 'sqlite:///marketlens_paper.db'


def is_cloud_database() -> bool:
    return database_url().startswith('postgresql+')


def get_engine():
    return create_engine(database_url(), pool_pre_ping=True, connect_args={'timeout': 20} if not is_cloud_database() else {})


def new_account(cash: float = 10_000.0, now: datetime | None = None) -> dict:
    now = now or datetime.now(ET)
    return dict(version=1, starting_balance=float(cash), cash=float(cash), positions={}, pending={},
                closed_trades=[], events=[], last_processed={}, watch_by_day={}, enabled=False,
                activated_at=None, created_at=now.isoformat(), settings={
                    'risk_percent': .5, 'exposure_percent': 10, 'max_trades_day': 2,
                    'max_daily_loss_percent': 1.0, 'max_positions': 2,
                    'slippage_bps': 5, 'fee_per_side': 0.0})


def init_db(engine):
    with engine.begin() as c:
        c.execute(text('CREATE TABLE IF NOT EXISTS paper_account (account_key VARCHAR(100) PRIMARY KEY, payload TEXT NOT NULL)'))
        c.execute(text('CREATE TABLE IF NOT EXISTS run_log (run_id VARCHAR(100) PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL)'))


def load_state(engine, account_key='default'):
    init_db(engine)
    with engine.begin() as c:
        row = c.execute(text('SELECT payload FROM paper_account WHERE account_key = :k'), {'k': account_key}).first()
    return json.loads(row[0]) if row else None


def save_state(engine, state, account_key='default'):
    init_db(engine)
    payload = json.dumps(state, allow_nan=False, separators=(',', ':'))
    with engine.begin() as c:
        c.execute(text('DELETE FROM paper_account WHERE account_key = :k'), {'k': account_key})
        c.execute(text('INSERT INTO paper_account(account_key, payload) VALUES (:k,:v)'), {'k': account_key, 'v': payload})


def export_state(state: dict) -> str:
    return json.dumps(state, indent=2, allow_nan=False)
