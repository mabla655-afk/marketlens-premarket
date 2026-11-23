"""Morning research and virtual-only example math (no brokerage orders or predictions)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import floor, isfinite
from typing import Any


@dataclass(frozen=True)
class VirtualPlan:
    shares: int
    entry_reference: float
    invalidation_reference: float
    target_2r: float
    virtual_notional: float
    virtual_risk_at_level: float
    virtual_budget: float
    virtual_risk_limit: float
    comment: str


def simulation_plan(entry: float | None, invalidation: float | None,
                    virtual_budget: float = 10_000, risk_percent: float = 0.5,
                    max_exposure_percent: float = 10.0) -> VirtualPlan | None:
    """Calculate virtual shares using risk and exposure ceilings, no position leverage.

    Pure arithmetic on supplied *reference levels*; neither price is an actual order quote.
    Rounding down means even a valid paper setup can result in 0 virtual shares.
    """
    if entry is None or invalidation is None:
        return None
    numbers = (entry, invalidation, virtual_budget, risk_percent, max_exposure_percent)
    if not all(isfinite(float(v)) for v in numbers):
        return None
    if entry <= 0 or invalidation <= 0 or invalidation >= entry or virtual_budget <= 0:
        return None
    if not 0 < risk_percent <= 5 or not 0 < max_exposure_percent <= 100:
        return None
    loss_per_share = float(entry - invalidation)
    virtual_risk_limit = float(virtual_budget * risk_percent / 100)
    virtual_exposure_limit = float(virtual_budget * max_exposure_percent / 100)
    shares = min(floor(virtual_risk_limit / loss_per_share), floor(virtual_exposure_limit / entry))
    shares = max(0, int(shares))
    return VirtualPlan(shares=shares, entry_reference=float(entry), invalidation_reference=float(invalidation),
                       target_2r=float(entry + 2 * loss_per_share), virtual_notional=round(shares * entry, 2),
                       virtual_risk_at_level=round(shares * loss_per_share, 2), virtual_budget=float(virtual_budget),
                       virtual_risk_limit=virtual_risk_limit,
                       comment=("No virtual position fits both limits." if shares == 0 else
                                "Illustration assumes exact reference fills; real gaps, spreads and slippage are excluded."))


def freshness_gate(observed_at: datetime | None, now: datetime, max_age_min: float = 25) -> bool:
    if observed_at is None or observed_at.date() != now.date():
        return False
    age = (now - observed_at).total_seconds() / 60
    return 0 <= age <= max_age_min


def morning_candidate(symbol: str, summary: dict[str, Any], now: datetime,
                      phase: str) -> dict[str, Any]:
    """Rank only *observed* premarket data. No stale quote as a morning pick."""
    result = dict(ticker=symbol, label="No current premarket data", rank=-1,
                  gap_pct=None, volume=None, observed_at=None, note="")
    if phase != "Premarket":
        result["note"] = "Morning scan is only active during today's 04:00–09:30 ET premarket."
        return result
    observed_at = summary.get("premarket_observed_at")
    if not freshness_gate(observed_at, now):
        result["note"] = "Premarket quote is missing or older than 25 minutes."
        return result
    gap = summary.get("premarket_gap_pct")
    volume = summary.get("premarket_volume")
    if gap is None or volume is None or not isfinite(float(gap)):
        result["note"] = "Provider did not supply a complete gap and volume observation."
        return result
    screen = summary.get("book_gapper", {}).get("checks", {})
    required = ["Gap magnitude ≥ 2%", "PM volume ≥ 100K by 9:00 ET",
                "20-day average volume > 500K", "14-day ATR ≥ $0.50"]
    met = sum(screen.get(key) is True for key in required)
    pending = sum(screen.get(key) is None for key in required)
    rank = met * 20 + min(12, abs(float(gap))) + (8 if volume >= 100_000 else 0)
    result.update(gap_pct=float(gap), volume=int(volume), observed_at=observed_at,
                  rank=round(rank, 1))
    if abs(gap) < 2:
        result["label"] = "Research only"
        result["note"] = "Today's observed gap is below the book's 2% screen."
    elif met >= 3 and pending == 0:
        result["label"] = "Priority watch"
        result["note"] = "Measurable premarket checks pass; news catalyst and chart quality are NOT verified."
    elif pending:
        result["label"] = "Early watch"
        result["note"] = "Gap detected; the 9 a.m. volume and/or other checks are pending."
    else:
        result["label"] = "Needs review"
        result["note"] = "Gap seen, but one or more measurable checks did not pass."
    return result


def simulate_exit_watch(held: dict | None, current_signal: dict) -> str:
    """Friendly educational status, not auto-close or instruction to transact."""
    if not held:
        return "No simulated position is open."
    if not current_signal.get("data_valid"):
        return "No fresh data: paper exit monitoring unavailable."
    close = current_signal.get("price")
    vwap = current_signal.get("vwap")
    if close is None or vwap is None:
        return "Insufficient data to evaluate hypothetical exit levels."
    if close < vwap:
        return "Review paper exit: the last completed close is below session VWAP."
    target = held.get("target_2r")
    if target and close >= target:
        return "Review paper exit: a hypothetical 2R reference level was reached."
    stop = held.get("invalidation_reference")
    if stop and close <= stop:
        return "Review paper exit: the hypothetical invalidation level was reached."
    return "No preset paper exit condition met on the latest completed candle."
